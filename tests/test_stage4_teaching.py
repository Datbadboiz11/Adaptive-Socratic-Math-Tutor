"""Grounded delivery, durable replay and report evidence on isolated PostgreSQL.

DB fixture embeddings are synthetic; direct/metadata serving never performs inference.
"""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from psycopg import sql,OperationalError
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT / 'backend',ROOT / 'tests'):
    sys.path.insert(0,str(path))
from app import sessions,tutor,teaching_runtime
from app.db import connect
from app.main import app
from app.manage import migrate,seed
from app.member2_runtime import seed_member2
from app.kb_projection import load_source,load_example_publications,load_profile,project
from app.kb_sync import sync_projection,activate_snapshot,withdraw_pack
from app.session_contracts import TeachingTurnRequest
from kb_support import FakeEmbedder


def test_no_rag_never_reads_retrieval_state_or_content(monkeypatch):
    def forbidden():
        raise AssertionError('No-RAG opened a content connection')
    monkeypatch.setattr(teaching_runtime,'connect',forbidden)
    result=teaching_runtime.retrieve_context({'teaching':{'mode':'no_rag','snapshot_id':'forbidden'},
                                             'policy':{'action':'hint'}})
    assert result['teaching_context']==[]
    assert result['retrieval']['retrieved_refs']==result['retrieval']['generator_refs']==[]


@pytest.mark.parametrize('action',['request_hint','request_explanation','request_example'])
def test_support_request_never_accepts_answer_steps(action):
    with pytest.raises(ValueError):
        TeachingTurnRequest(request_id=uuid4(),opportunity_id=uuid4(),expected_state_version=1,
                            action=action,steps=['injected answer'])


@pytest.fixture(scope='module')
def database():
    if not os.getenv('RUN_DB_TESTS'):
        pytest.skip('PostgreSQL requires RUN_DB_TESTS=1')
    name='test_stage4_'+uuid4().hex
    with connect() as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    with pytest.MonkeyPatch.context() as env:
        env.setenv('PGOPTIONS','-c search_path='+name)
        env.setenv('DEMO_MODE','true')
        env.setenv('TUTOR_ENABLED','true')
        env.setenv('TUTOR_RAG_MODE','full')
        env.setenv('LLM_ENABLED','false')
        env.setenv('VALIDATOR_TIMEOUT_SECONDS','3')
        try:
            with connect() as connection:
                migrate(connection)
                seed(connection)
                seed_member2(connection)
            registry,bank,origin=load_source('member2-v2')
            projection=project(registry,bank,load_profile(),origin=origin,
                               examples=load_example_publications('member2-v2'))
            sync_projection(projection,FakeEmbedder(projection.profile),activate=True)
            yield projection,bank
        finally:
            with connect() as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))


@pytest.fixture
def learner(database):
    student='STAGE4-'+uuid4().hex
    with connect() as connection:
        connection.execute('INSERT INTO profiles(student_id,display_name) VALUES (%s,%s)',(student,'Synthetic Stage 4'))
    with TestClient(app) as client:
        token=client.post('/api/v1/demo/login',json={'demo_profile_id':student}).json()['access_token']
        yield client,{'Authorization':'Bearer '+token},student


def start(learner,concept='N02'):
    client,headers,student=learner
    response=client.post('/api/v1/sessions',headers=headers,json={
        'request_id':str(uuid4()),'demo_profile_id':student,'topic_id':'TOPIC-'+concept})
    assert response.status_code==201,response.text
    return response.json()


def send(learner,session,action='submit',steps=None):
    client,headers,_=learner
    body={'request_id':str(uuid4()),'expected_state_version':session['state_version'],
          'opportunity_id':session['current_opportunity_id'],'action':action,'steps':steps or []}
    response=client.post(f"/api/v1/sessions/{session['session_id']}/turns",headers=headers,json=body)
    assert response.status_code==200,response.text
    return response.json(),body


@pytest.mark.parametrize('concept',[pack.concept_id for pack in load_source('member2-v2')[1].packs])
def test_wrong_kb_hint_correct_new_independent_report(learner,database,concept):
    client,headers,_=learner
    pack=next(p for p in database[1].packs if p.concept_id==concept)
    session=start(learner,concept)
    wrong,_=send(learner,session,steps=pack.errors[0].response_steps)
    assert wrong['response_source']=='reviewed_kb' and wrong['observation'] is None
    assert wrong['message']==pack.hints[0].text
    assert wrong['session']['assistance_received']
    assert wrong['tutor']['content_refs'][0]['content_id']==concept+'-hint-1'
    with connect() as connection:
        pipeline=connection.execute('SELECT pipeline FROM turns WHERE request_id=%s',(wrong['session']['turns'][-1]['request_id'],)).fetchone()['pipeline']
    assert pipeline['retrieval']['retrieved_refs']==pipeline['retrieval']['generator_refs']==pipeline['retrieval']['delivered_refs']
    fixed,_=send(learner,wrong['session'],steps=[pack.problems[0].reference_answer])
    session=fixed['session']
    for _ in range(2):
        response=client.post(f"/api/v1/sessions/{session['session_id']}/next",headers=headers,
            json={'request_id':str(uuid4()),'expected_state_version':session['state_version']})
        assert response.status_code==200,response.text
        session=response.json()
    independent,_=send(learner,session,steps=[pack.problems[2].reference_answer])
    response=client.post(f"/api/v1/sessions/{session['session_id']}/finish",headers=headers,
        json={'request_id':str(uuid4()),'expected_state_version':independent['session']['state_version']})
    assert response.status_code==200,response.text
    report=response.json()
    assert (report['independent_correct'],report['assisted_correct'],report['valid_observations'])==(1,1,0)
    assert report['skills'][0]['mastery_before'] is None
    assert report['skills'][0]['incorrect_submissions']==1 and report['skills'][0]['evidence_turn_ids']
    assert client.get(f"/api/v1/sessions/{session['session_id']}/report",headers=headers).json()==report


def test_level_zero_help_is_persisted_and_not_counted_as_independent(learner,database):
    result,_=send(learner,start(learner),'request_explanation')
    assert result['response_source']=='reviewed_kb'
    assert result['session']['hint_level']==0 and result['session']['assistance_received']
    pack=next(p for p in database[1].packs if p.concept_id=='N02')
    solved,_=send(learner,result['session'],steps=[pack.problems[0].reference_answer])
    with connect() as connection:
        outcome=connection.execute('SELECT outcome FROM opportunities WHERE opportunity_id=%s',
                                   (solved['session']['current_opportunity_id'],)).fetchone()['outcome']
    assert outcome=='assisted_correct' and solved['observation'] is None


def test_example_exclusions_and_retrieved_vs_used_refs(learner):
    session=start(learner)
    result,_=send(learner,session,'request_example')
    assert result['tutor']['action']=='different_example' and result['session']['hint_level']==3
    assert len(result['tutor']['content_refs'])==1
    with connect() as connection:
        row=connection.execute('SELECT pipeline FROM turns WHERE session_id=%s',(session['session_id'],)).fetchone()
        delivery=connection.execute('SELECT d.* FROM teaching_deliveries d JOIN turns t USING(turn_id) WHERE t.session_id=%s',
                                    (session['session_id'],)).fetchone()
    trace=row['pipeline']['retrieval']
    assert len(trace['retrieved_refs'])==2 and len(trace['generator_refs'])==len(trace['delivered_refs'])==1
    assert delivery['family_id']!=session['problem']['family_id']
    serialized=json.dumps(result)
    assert all(key not in serialized for key in ('reference_answer','reference_steps','teaching_context','registry_hash'))


def test_no_rag_and_mode_are_pinned_per_session(learner,monkeypatch):
    monkeypatch.setenv('TUTOR_RAG_MODE','no_rag')
    session=start(learner)
    monkeypatch.setenv('TUTOR_RAG_MODE','full')
    def forbidden(*args,**kwargs): raise AssertionError('No-RAG performed retrieval')
    monkeypatch.setattr('app.teaching_runtime.KBRetriever.retrieve',forbidden)
    result,_=send(learner,session,'request_hint')
    assert result['response_source']=='reviewed_hint' and not result['tutor']['content_refs']
    assert result['session']['rag_mode']=='no_rag'


def test_replay_after_snapshot_change_never_retrieves_again(learner,database,monkeypatch):
    client,headers,_=learner
    session=start(learner)
    result,body=send(learner,session,'request_hint')
    projection=database[0]
    from dataclasses import replace
    changed=replace(projection,chunks=projection.chunks[:-1])
    sync_projection(changed,FakeEmbedder(changed.profile),activate=True)
    try:
        def forbidden(*args,**kwargs): raise AssertionError('Replay called retrieval')
        monkeypatch.setattr(teaching_runtime,'retrieve_context',forbidden)
        replay=client.post(f"/api/v1/sessions/{session['session_id']}/turns",headers=headers,json=body)
        assert replay.json()==result
    finally:
        activate_snapshot('runtime',projection.snapshot_id)


def test_failed_business_commit_does_not_record_delivery_and_reuses_prepared(learner,monkeypatch):
    client,headers,_=learner
    session=start(learner)
    body={'request_id':str(uuid4()),'expected_state_version':session['state_version'],
          'opportunity_id':session['current_opportunity_id'],'action':'request_explanation','steps':[]}
    url=f"/api/v1/sessions/{session['session_id']}/turns"
    original=sessions.advance
    def fail(*args,**kwargs): raise OperationalError('Synthetic failure after delivery insert')
    monkeypatch.setattr(sessions,'advance',fail)
    assert client.post(url,headers=headers,json=body).status_code==503
    with connect() as connection:
        op=connection.execute('SELECT assistance_received FROM opportunities WHERE opportunity_id=%s',(session['current_opportunity_id'],)).fetchone()
        assert not op['assistance_received']
        assert connection.execute('SELECT count(*) AS n FROM turns WHERE session_id=%s',(session['session_id'],)).fetchone()['n']==0
    monkeypatch.setattr(sessions,'advance',original)
    def forbidden(*args): raise AssertionError('Prepared result was recomputed')
    monkeypatch.setattr(tutor,'run_graph',forbidden)
    retried=client.post(url,headers=headers,json=body)
    assert retried.status_code==200 and retried.json()['session']['assistance_received']


def test_report_is_frozen_and_another_profile_cannot_read_it(learner):
    client,headers,_=learner
    session=start(learner)
    result,_=send(learner,session,steps=['0'])
    report=client.post(f"/api/v1/sessions/{session['session_id']}/finish",headers=headers,json={
        'request_id':str(uuid4()),'expected_state_version':result['session']['state_version']}).json()
    client.post('/api/v1/demo/login',json={'demo_profile_id':'DEMO-STUDENT-02'})
    token=client.post('/api/v1/demo/login',json={'demo_profile_id':'DEMO-STUDENT-02'}).json()['access_token']
    assert client.get(f"/api/v1/sessions/{session['session_id']}/report",headers={'Authorization':'Bearer '+token}).status_code==404
    assert client.get(f"/api/v1/sessions/{session['session_id']}/report",headers=headers).json()==report


def test_retrieval_failure_keeps_grading_without_fabricated_delivery(learner,monkeypatch):
    def unavailable(*args,**kwargs): raise TimeoutError('Synthetic KB outage')
    monkeypatch.setattr('app.teaching_runtime.KBRetriever.retrieve',unavailable)
    result,_=send(learner,start(learner),steps=['0'])
    assert result['assessment']['assessment_status']=='verified_incorrect'
    assert result['response_source']=='assessment_feedback' and not result['tutor']['content_refs']
    assert not result['session']['assistance_received'] and result['session']['hint_level']==0


def test_legacy_report_has_diagnosis_evidence_parameter_provenance_and_frozen_correction(learner):
    from app.knowledge import PARAMETERS
    client,headers,_=learner
    session=start(learner,'LINEAR-01')
    bank=json.loads((ROOT/'content/linear_equations.v1.json').read_text(encoding='utf-8'))['problems']
    problem=next(p for p in bank if p['problem_id']==session['problem']['problem_id'])
    wrong,_=send(learner,session,steps=problem['common_errors'][0]['steps'])
    assert wrong['assessment']['diagnosis_status']=='suspected'
    fixed,_=send(learner,wrong['session'],steps=problem['reference_methods'][0]['steps'])
    response=client.post(f"/api/v1/sessions/{session['session_id']}/finish",headers=headers,json={
        'request_id':str(uuid4()),'expected_state_version':fixed['session']['state_version']})
    assert response.status_code==200,response.text
    report=response.json(); skill=report['skills'][0]
    assert report['report_version']=='learning-report-2.1.0'
    assert [d['status'] for d in skill['diagnoses']]==['suspected','rejected']
    ids={t['turn_id'] for t in report['timeline']}
    assert all(e['turn_id'] in ids for d in skill['diagnoses'] for e in d['evidence'])
    assert skill['parameter_version']==PARAMETERS['parameter_version']
    assert skill['parameter_source']==PARAMETERS['source'] and skill['updated_at']
    with connect() as connection:
        stored=connection.execute('SELECT payload FROM session_reports WHERE session_id=%s',
                                  (session['session_id'],)).fetchone()['payload']
    assert stored==report
    assert client.get(f"/api/v1/sessions/{session['session_id']}/report",headers=headers).json()==report


def test_withdrawal_after_retrieval_cannot_be_delivered(learner,monkeypatch,database):
    client,headers,_=learner
    session=start(learner)
    original=tutor.run_graph
    def withdraw_before_commit(*args):
        prepared=original(*args)
        withdraw_pack('runtime','N02',database[0].registry.content_version,'Synthetic concurrent withdrawal','Stage 4 test')
        return prepared
    monkeypatch.setattr(tutor,'run_graph',withdraw_before_commit)
    response=client.post(f"/api/v1/sessions/{session['session_id']}/turns",headers=headers,json={
        'request_id':str(uuid4()),'expected_state_version':session['state_version'],
        'opportunity_id':session['current_opportunity_id'],'action':'request_explanation','steps':[]})
    assert response.status_code==409 and response.json()['code']=='teaching_content_changed'
    with connect() as connection:
        assert not connection.execute('SELECT assistance_received FROM opportunities WHERE opportunity_id=%s',
                                      (session['current_opportunity_id'],)).fetchone()['assistance_received']
