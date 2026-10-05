"""Integration tests use an isolated PostgreSQL schema, never existing demo sessions."""
import json
import os
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.main import app
from app.db import connect
from app.manage import migrate, seed, CONTENT
from app import sessions as service

pytestmark = pytest.mark.skipif(not os.environ.get('RUN_DB_TESTS'), reason='Set RUN_DB_TESTS=1 and PostgreSQL connection variables')


@pytest.fixture(scope='module', autouse=True)
def isolated_schema():
    schema = 'test_phase2_' + uuid4().hex
    original = os.environ.get('PGOPTIONS')
    with connect() as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    os.environ['PGOPTIONS'] = f'-c search_path={schema}'
    os.environ['DEMO_MODE'] = 'true'
    try:
        with connect() as c:
            migrate(c)
            seed(c)
        yield
    finally:
        if original is None:
            os.environ.pop('PGOPTIONS', None)
        else:
            os.environ['PGOPTIONS'] = original
        assert schema.startswith('test_phase2_') and len(schema) == 44
        with connect() as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@pytest.fixture
def client():
    old=os.environ.get('TUTOR_ENABLED')
    os.environ['TUTOR_ENABLED']='false'
    try:
        with TestClient(app) as c:
            yield c
    finally:
        if old is None: os.environ.pop('TUTOR_ENABLED',None)
        else: os.environ['TUTOR_ENABLED']=old


def auth(client, profile='DEMO-STUDENT-01'):
    response = client.post('/api/v1/demo/login', json={'demo_profile_id': profile})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def create(client, headers):
    body = {'request_id': str(uuid4()), 'demo_profile_id': 'DEMO-STUDENT-01', 'topic_id': 'TOPIC-LINEAR-01'}
    response = client.post('/api/v1/sessions', json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def body(s, **extra):
    return {'request_id': str(uuid4()), 'expected_state_version': s['state_version'], **extra}


def mutate(client, headers, s, endpoint, **extra):
    method = client.put if endpoint == 'draft' else client.post
    response = method(f"/api/v1/sessions/{s['session_id']}/{endpoint}", json=body(s, **extra), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_seed_and_migrate_repeat_without_duplicates():
    with connect() as c:
        assert migrate(c) == []
        assert seed(c)['inserted'] == 0
        assert c.execute('SELECT count(*) n FROM problems').fetchone()['n'] == 6
        assert c.execute('SELECT count(*) n FROM profiles').fetchone()['n'] == 2


def test_seed_refuses_changed_version(tmp_path):
    data = json.loads(CONTENT.read_text(encoding='utf-8'))
    data['problems'][0]['prompt'] += ' changed'
    target = tmp_path / 'changed.json'
    target.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='immutable'):
        with connect() as c:
            seed(c, target)
    with connect() as c:
        assert c.execute('SELECT count(*) n FROM problems').fetchone()['n'] == 6


def test_create_retry_and_no_private_fields(client):
    h = auth(client)
    b = {'request_id': str(uuid4()), 'demo_profile_id': 'DEMO-STUDENT-01', 'topic_id': 'TOPIC-LINEAR-01'}
    a = client.post('/api/v1/sessions', json=b, headers=h)
    retry = client.post('/api/v1/sessions', json=b, headers=h)
    assert a.json() == retry.json()
    assert a.status_code == 201
    problem = a.json()['problem']
    assert not {'reference_answer','reference_methods','hint_ladder','common_errors','private_payload'}.intersection(problem)
    assert a.json()['review_status'] == 'draft'
    changed = client.post('/api/v1/sessions', json={**b, 'topic_id': 'bad'}, headers=h)
    assert changed.status_code == 409 and changed.json()['code'] == 'idempotency_conflict'


def test_draft_pause_resume_preserves_whitespace_and_opportunity(client):
    h = auth(client); s = create(client, h)
    op = s['current_opportunity_id']
    text = '  3x = 15\n\nx = 5  '
    s = mutate(client, h, s, 'draft', draft=text)
    s = mutate(client, h, s, 'pause')
    assert s['status'] == 'paused' and s['draft'] == text
    read = client.get(f"/api/v1/sessions/{s['session_id']}", headers=h).json()
    assert read == s
    s = mutate(client, h, s, 'resume')
    assert s['draft'] == text and s['current_opportunity_id'] == op and s['eligible_observations'] == 0


def test_submit_retry_and_report_do_not_invent_learning(client):
    h = auth(client); s = create(client, h)
    b = body(s, opportunity_id=s['current_opportunity_id'], action='submit', steps=['3x = 15','x = 5'])
    url = f"/api/v1/sessions/{s['session_id']}/turns"
    first = client.post(url, json=b, headers=h)
    retry = client.post(url, json=b, headers=h)
    assert first.json() == retry.json()
    result = first.json(); s = result['session']
    assert result['assessment']['assessment_status'] == 'unverified'
    assert result['eligibility'] == {'eligible': False, 'reason': 'not_verified'}
    s = mutate(client, h, s, 'turns', opportunity_id=s['current_opportunity_id'], action='request_hint', steps=[])['session']
    assert s['hint_level'] == 0
    report = mutate(client, h, s, 'finish')
    assert report['submitted_turns'] == report['unverified_submissions'] == report['requested_hints'] == 1
    assert report['valid_observations'] == report['independent_correct'] == report['assisted_correct'] == 0
    assert mutate(client, h, s, 'finish') == report
    with connect() as c:
        assert c.execute('SELECT count(*) n FROM mastery_history').fetchone()['n'] == 0


def test_concurrent_same_request_is_committed_once(client):
    h = auth(client); s = create(client, h)
    payload = body(s, opportunity_id=s['current_opportunity_id'], action='submit', steps=['x=5'])
    def send():
        with TestClient(app) as c:
            return c.post(f"/api/v1/sessions/{s['session_id']}/turns", headers=h, json=payload)
    with ThreadPoolExecutor(2) as pool:
        a, b = list(pool.map(lambda _: send(), range(2)))
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert len(a.json()['session']['turns']) == 1


def test_concurrent_different_requests_one_version_wins(client):
    h = auth(client); s = create(client, h)
    def send(text):
        with TestClient(app) as c:
            return c.put(f"/api/v1/sessions/{s['session_id']}/draft", headers=h, json=body(s, draft=text))
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(send, ['first', 'second']))
    assert sorted(r.status_code for r in responses) == [200, 409]
    state = client.get(f"/api/v1/sessions/{s['session_id']}", headers=h).json()
    assert state['state_version'] == 2


def test_other_profile_cannot_read_or_change_session(client):
    a, b = auth(client), auth(client, 'DEMO-STUDENT-02')
    s = create(client, a)
    for url in [f"/api/v1/sessions/{s['session_id']}", f"/api/v1/sessions/{s['session_id']}/report"]:
        assert client.get(url, headers=b).status_code == 404
    assert client.put(f"/api/v1/sessions/{s['session_id']}/draft", headers=b, json=body(s, draft='attack')).status_code == 404
    assert client.get('/api/v1/sessions', headers=b).json() == []
    assert client.get('/api/v1/sessions').status_code == 401


def test_next_exhaustion_and_closed_session(client):
    h = auth(client); s = create(client, h)
    ids = [s['problem']['problem_id']]
    for _ in range(5):
        s = mutate(client, h, s, 'next'); ids.append(s['problem']['problem_id'])
    assert len(set(ids)) == 6 and s['available_next'] == 0
    response = client.post(f"/api/v1/sessions/{s['session_id']}/next", headers=h, json=body(s))
    assert response.status_code == 409 and response.json()['code'] == 'content_exhausted'
    mutate(client, h, s, 'finish')
    current = client.get(f"/api/v1/sessions/{s['session_id']}", headers=h).json()
    assert client.put(f"/api/v1/sessions/{s['session_id']}/draft", headers=h, json=body(current, draft='late')).status_code == 409


def test_failed_mutation_rolls_back_and_retry_can_succeed(client, monkeypatch):
    h = auth(client); s = create(client, h)
    payload = body(s, opportunity_id=s['current_opportunity_id'], action='submit', steps=['x=5'])
    original = service.advance
    def fail(*args, **kwargs):
        raise psycopg.OperationalError('simulated failure after inserting turn')
    monkeypatch.setattr(service, 'advance', fail)
    url = f"/api/v1/sessions/{s['session_id']}/turns"
    assert client.post(url, json=payload, headers=h).status_code == 503
    with connect() as c:
        assert c.execute('SELECT count(*) n FROM turns WHERE session_id=%s', (s['session_id'],)).fetchone()['n'] == 0
    monkeypatch.setattr(service, 'advance', original)
    response = client.post(url, json=payload, headers=h)
    assert response.status_code == 200 and len(response.json()['session']['turns']) == 1


def test_schema_observation_unique_and_atomic_history(client):
    h = auth(client); s = create(client, h)
    result = mutate(client, h, s, 'turns', opportunity_id=s['current_opportunity_id'], action='submit', steps=['x=5'])
    turn = result['session']['turns'][0]['turn_id']
    # Synthetic constraint fixture, not a learning outcome from the unavailable pipeline.
    with connect() as c:
        with pytest.raises(psycopg.errors.UniqueViolation):
            with c.transaction():
                for _ in range(2):
                    observation_id = uuid4()
                    c.execute('''INSERT INTO observations(observation_id,student_id,opportunity_id,skill_id,turn_id,correct,
                        prediction_before,mastery_before,mastery_after,parameter_version,protocol_version)
                        VALUES (%s,%s,%s,%s,%s,true,0.5,0.5,0.6,'test-only','g2-v1')''',
                        (observation_id, 'DEMO-STUDENT-01', s['current_opportunity_id'], 'SK-LIN-SOLVE', turn))
                    c.execute('INSERT INTO mastery_history(observation_id,state_before,state_after) VALUES (%s,%s,%s)',
                              (observation_id, Jsonb({'test': 0.5}), Jsonb({'test': 0.6})))
        assert c.execute('SELECT count(*) n FROM observations WHERE opportunity_id=%s', (s['current_opportunity_id'],)).fetchone()['n'] == 0
        assert c.execute('SELECT count(*) n FROM mastery_history').fetchone()['n'] == 0


def test_demo_disabled_and_invalid_payload(client, monkeypatch):
    h = auth(client)
    assert client.post('/api/v1/sessions', headers=h, json={'unexpected': True}).status_code == 422
    monkeypatch.setenv('DEMO_MODE', 'false')
    assert client.get('/api/v1/demo/profiles').status_code == 403
    assert client.get('/api/v1/sessions', headers=h).status_code == 403
