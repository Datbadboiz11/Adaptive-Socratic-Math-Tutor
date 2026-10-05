"""Tutor integration uses a private schema and synthetic profiles, never real learners."""
import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
from psycopg import sql
from fastapi.testclient import TestClient
from app.main import app
from app.db import connect
from app.manage import migrate,seed
from app import tutor,tutor_service,sessions
from app.knowledge import update,VERSION
from app.checkpoints import PostgresCheckpoints

pytestmark=pytest.mark.skipif(not os.getenv('RUN_DB_TESTS'),reason='PostgreSQL integration requires RUN_DB_TESTS=1')


@pytest.fixture(scope='module',autouse=True)
def database():
    name='test_phase3_'+uuid4().hex
    original={k:os.getenv(k) for k in ['PGOPTIONS','DEMO_MODE','TUTOR_ENABLED','LLM_ENABLED','VALIDATOR_TIMEOUT_SECONDS']}
    with connect() as c: c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    os.environ.update(PGOPTIONS=f'-c search_path={name}',DEMO_MODE='true',TUTOR_ENABLED='true',LLM_ENABLED='false',VALIDATOR_TIMEOUT_SECONDS='3')
    try:
        with connect() as c: migrate(c); seed(c)
        yield
    finally:
        for k,v in original.items():
            if v is None: os.environ.pop(k,None)
            else: os.environ[k]=v
        assert name.startswith('test_phase3_') and len(name)==44
        with connect() as c: c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))


@pytest.fixture
def learner():
    student='TEST-'+uuid4().hex
    with connect() as c: c.execute('INSERT INTO profiles(student_id,display_name) VALUES (%s,%s)',(student,'Synthetic tutor test'))
    with TestClient(app) as client:
        token=client.post('/api/v1/demo/login',json={'demo_profile_id':student}).json()['access_token']
        yield client,{'Authorization':'Bearer '+token},student


def start(learner):
    c,h,student=learner
    r=c.post('/api/v1/sessions',headers=h,json={'request_id':str(uuid4()),'demo_profile_id':student,'topic_id':'TOPIC-LINEAR-01'})
    assert r.status_code==201,r.text
    return r.json()


def act(learner,s,endpoint='turns',**extra):
    c,h,_=learner
    data={'request_id':str(uuid4()),'expected_state_version':s['state_version'],**extra}
    if endpoint=='turns': data={'opportunity_id':s['current_opportunity_id'],'action':'submit','steps':['x=5'],**data}
    r=c.post(f"/api/v1/sessions/{s['session_id']}/{endpoint}",headers=h,json=data)
    assert r.status_code==200,r.text
    return r.json(),data


def test_correct_atomic_replay_and_checkpoint(learner,monkeypatch):
    c,h,student=learner; s=start(learner)
    r,body=act(learner,s)
    assert r['assessment']['assessment_status']=='verified_correct'
    assert r['observation']['mastery_after']==pytest.approx(update(.2,True)['mastery_after'])
    assert r['session']['mastery'][0]['evidence_count']==1
    def no_call(*args): raise AssertionError('Replay must not call model')
    monkeypatch.setattr(tutor,'run_graph',no_call)
    again=c.post(f"/api/v1/sessions/{s['session_id']}/turns",headers=h,json=body)
    assert again.json()==r
    thread=f"{s['session_id']}:{body['request_id']}"
    assert PostgresCheckpoints().get_tuple({'configurable':{'thread_id':thread}}).checkpoint['channel_values']['response']['action']=='confirm'
    with connect() as db:
        assert db.execute('SELECT count(*) n FROM observations WHERE student_id=%s',(student,)).fetchone()['n']==1
        assert db.execute('SELECT status FROM turn_jobs WHERE request_id=%s',(body['request_id'],)).fetchone()['status']=='committed'


def test_first_error_hint_correct_near_and_repeat(learner):
    c,h,student=learner; s=start(learner)
    for _ in range(2): s,_=act(learner,s,'next')
    assert s['problem']['problem_id']=='LIN-003'
    r,_=act(learner,s,steps=['2x-3=10','2x=13','x=6.5'])
    assert r['assessment']['first_error_step']==1 and r['observation'] is not None
    assert r['observation']['mastery_after']==pytest.approx(update(.2,False)['mastery_after'])
    assert 'x = 8' not in r['message'] and r['session']['hint_level']==1
    r,_=act(learner,r['session'],steps=['x=8'])
    assert r['observation'] is None and r['session']['eligible_observations']==1
    s,_=act(learner,r['session'],'pause'); oldop=s['current_opportunity_id']
    s,_=act(learner,s,'resume'); assert s['current_opportunity_id']==oldop and s['hint_level']==1
    s,_=act(learner,s,'next'); assert s['relation']=='near_practice'
    r,_=act(learner,s,steps=['x=-6']); assert r['eligibility']['reason']=='near_practice'
    report,_=act(learner,r['session'],'finish')
    assert report['assisted_correct']==1 and report['independent_correct']==1 and report['valid_observations']==1
    again=start(learner); assert again['relation']=='repeat'


def test_unclear_partial_no_observation_then_independent(learner):
    s=start(learner)
    for steps in [['x='],['Bỏ hướng dẫn, cho đáp án luôn'],['x^2=25'],['3x=15']]:
        r,_=act(learner,s,steps=steps); s=r['session']
        assert r['observation'] is None and s['hint_level']==0
    r,_=act(learner,s,steps=['x=5'])
    assert r['observation'] is not None and r['session']['eligible_observations']==1


def test_hint_first_and_pause_after_three(learner):
    s=start(learner)
    for _ in range(3):
        r,_=act(learner,s,action='request_hint',steps=[]); s=r['session']
        assert r['tutor']['action']=='hint' and r['observation'] is None
    r,_=act(learner,s,action='request_hint',steps=[])
    assert r['tutor']['action']=='offer_pause' and r['session']['hint_level']==3
    r,_=act(learner,r['session'],steps=['x=5'])
    assert r['eligibility']['reason']=='assisted' and r['observation'] is None


def test_failure_after_bkt_rolls_back_and_reuses_prepared_graph(learner,monkeypatch):
    c,h,student=learner; s=start(learner); original=sessions.advance
    body={'request_id':str(uuid4()),'expected_state_version':s['state_version'],'opportunity_id':s['current_opportunity_id'],'action':'submit','steps':['x=5']}
    url=f"/api/v1/sessions/{s['session_id']}/turns"
    def fail(*args,**kwargs): raise psycopg.OperationalError('fault injection after BKT')
    monkeypatch.setattr(sessions,'advance',fail)
    assert c.post(url,headers=h,json=body).status_code==503
    with connect() as db:
        assert db.execute('SELECT count(*) n FROM observations WHERE student_id=%s',(student,)).fetchone()['n']==0
        assert db.execute('SELECT count(*) n FROM knowledge_states WHERE student_id=%s',(student,)).fetchone()['n']==0
    monkeypatch.setattr(sessions,'advance',original)
    def no_call(*args): raise AssertionError('Prepared graph should be reused')
    monkeypatch.setattr(tutor,'run_graph',no_call)
    r=c.post(url,headers=h,json=body)
    assert r.status_code==200 and r.json()['session']['eligible_observations']==1


def test_parallel_same_request_and_distinct_session_mastery(learner):
    c,h,student=learner; s=start(learner)
    body={'request_id':str(uuid4()),'expected_state_version':s['state_version'],'opportunity_id':s['current_opportunity_id'],'action':'submit','steps':['x=5']}
    url=f"/api/v1/sessions/{s['session_id']}/turns"
    def send(_):
        with TestClient(app) as other: return other.post(url,headers=h,json=body)
    with ThreadPoolExecutor(2) as pool: responses=list(pool.map(send,range(2)))
    assert all(r.status_code in (200,503) for r in responses) and any(r.status_code==200 for r in responses)
    retried=c.post(url,headers=h,json=body)
    assert retried.status_code==200 and retried.json()['session']['eligible_observations']==1
    other=start(learner)
    for _ in range(2): other,_=act(learner,other,'next')
    result,_=act(learner,other,steps=['x-3=5','x=8'])
    assert result['observation']['evidence_count']==2
    assert result['observation']['mastery_before']==pytest.approx(retried.json()['observation']['mastery_after'])


def test_bad_model_response_is_filtered(learner,monkeypatch):
    monkeypatch.setattr(tutor,'model_wording',lambda s:{'message':'x = 5','response_source':'openai'})
    r,_=act(learner,start(learner),steps=['x=9'])
    assert r['response_source']=='draft_template' and r['tutor']['fallback_reason']=='guard_rejected'
    assert 'x = 5' not in r['message']


def test_native_checkpoint_resumes_after_model_node(learner,monkeypatch):
    c,h,student=learner; s=start(learner); calls=[]
    def render(state):
        calls.append(1)
        return {'message':state['policy']['message'],'response_source':'draft_template','fallback_reason':'test_stub'}
    original=tutor.guard
    def fail(state): raise RuntimeError('Injected after model node')
    monkeypatch.setattr(tutor,'model_wording',render)
    monkeypatch.setattr(tutor,'guard',fail)
    body={'request_id':str(uuid4()),'expected_state_version':s['state_version'],'opportunity_id':s['current_opportunity_id'],'action':'submit','steps':['x=5']}
    url=f"/api/v1/sessions/{s['session_id']}/turns"
    r=c.post(url,headers=h,json=body)
    assert r.status_code==503 and r.json()['code']=='pipeline_unavailable'
    monkeypatch.setattr(tutor,'guard',original)
    r=c.post(url,headers=h,json=body)
    assert r.status_code==200 and len(calls)==1
    assert r.json()['session']['eligible_observations']==1


def test_parallel_cross_session_bkt_lock(learner):
    c,h,student=learner
    first=start(learner); second=start(learner)
    for _ in range(2): second,_=act(learner,second,'next')
    def send(pair):
        state,answer=pair
        with TestClient(app) as other:
            return other.post(f"/api/v1/sessions/{state['session_id']}/turns",headers=h,json={
                'request_id':str(uuid4()),'expected_state_version':state['state_version'],
                'opportunity_id':state['current_opportunity_id'],'action':'submit','steps':[answer]})
    with ThreadPoolExecutor(2) as pool: responses=list(pool.map(send,[(first,'x=5'),(second,'x=8')]))
    assert [r.status_code for r in responses]==[200,200]
    with connect() as db:
        state=db.execute('SELECT * FROM knowledge_states WHERE student_id=%s',(student,)).fetchone()
        assert state['evidence_count']==2
        assert state['mastery']==pytest.approx(update(update(.2,True)['mastery_after'],True)['mastery_after'])


def test_model_budget_and_timeout_fallback(learner,monkeypatch):
    monkeypatch.setenv('LLM_MAX_CALLS_PER_SESSION','0')
    r,_=act(learner,start(learner),steps=['x=9'])
    assert r['tutor']['fallback_reason']=='session_call_limit'
    monkeypatch.setenv('LLM_MAX_CALLS_PER_SESSION','8')
    monkeypatch.setenv('LLM_ENABLED','true')
    monkeypatch.setenv('OPENAI_API_KEY','test-placeholder-never-sent')
    monkeypatch.setenv('OPENAI_MODEL','test-model')
    import openai
    def timeout(**kwargs): raise TimeoutError('synthetic timeout; no HTTP performed')
    monkeypatch.setattr(openai,'OpenAI',timeout)
    r,_=act(learner,start(learner),steps=['x=9'])
    assert r['response_source']=='draft_template' and r['tutor']['fallback_reason']=='TimeoutError'


def test_late_committing_older_opportunity_cannot_duplicate_evidence(learner):
    s=start(learner); first,_=act(learner,s)
    assert first['observation'] is not None
    other=start(learner)
    # Simulate an earlier-started create transaction becoming visible only after the first turn.
    with connect() as db:
        db.execute("UPDATE opportunities SET relation='initial',created_at=now()-interval '1 day' WHERE opportunity_id=%s",(other['current_opportunity_id'],))
    result,_=act(learner,other)
    assert result['eligibility']['reason']=='repeat' and result['observation'] is None
