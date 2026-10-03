"""Run Phase 5 technical acceptance cases in a disposable PostgreSQL schema.

These are API/DB checks, not a substitute for the required manual browser run.
No model HTTP call is made and no token or database password is written to evidence.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
values = {}
for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
os.environ.update(
    PGHOST='127.0.0.1', PGPORT=values.get('POSTGRES_PORT', '5433'),
    PGDATABASE=values.get('POSTGRES_DB', 'mo_tutor_dev'),
    PGUSER=values.get('POSTGRES_USER', 'mo_dev'),
    PGPASSWORD=values['POSTGRES_PASSWORD'], PGOPTIONS='',
    DEMO_MODE='true', TUTOR_ENABLED='true', LLM_ENABLED='false',
    VALIDATOR_TIMEOUT_SECONDS='3',
)
os.environ.pop('DATABASE_URL', None)

from fastapi.testclient import TestClient  # noqa: E402
from psycopg import sql  # noqa: E402
from app.db import connect  # noqa: E402
from app.main import app  # noqa: E402
from app.manage import migrate, seed  # noqa: E402
from app.knowledge import VERSION as BKT_VERSION  # noqa: E402
from app.math_validator import VERSION as VALIDATOR_VERSION  # noqa: E402

schema = 'test_phase5_' + uuid4().hex
with connect() as connection:
    connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
os.environ['PGOPTIONS'] = f'-c search_path={schema}'
checks = []


def add_case(case_id, actual):
    checks.append({'id': case_id, 'result': 'PASS', 'actual': actual})


def new_learner(client):
    student = 'ACCEPT-' + uuid4().hex
    with connect() as connection:
        connection.execute('INSERT INTO profiles(student_id,display_name) VALUES (%s,%s)',
                           (student, 'Synthetic acceptance learner'))
    token = client.post('/api/v1/demo/login', json={'demo_profile_id': student}).json()['access_token']
    headers = {'Authorization': 'Bearer ' + token}
    response = client.post('/api/v1/sessions', headers=headers, json={
        'request_id': str(uuid4()), 'demo_profile_id': student, 'topic_id': 'TOPIC-LINEAR-01'})
    assert response.status_code == 201, response.text
    return student, headers, response.json()


def mutate(client, headers, session, endpoint, **extra):
    body = {'request_id': str(uuid4()), 'expected_state_version': session['state_version'], **extra}
    if endpoint == 'turns':
        body = {'opportunity_id': session['current_opportunity_id'],
                'action': 'submit', 'steps': [], **body}
    response = client.post(f"/api/v1/sessions/{session['session_id']}/{endpoint}",
                           headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def at_lin003(client, headers, session):
    for _ in range(2):
        session, _ = mutate(client, headers, session, 'next')
    assert session['problem']['problem_id'] == 'LIN-003'
    return session


def counts(student):
    with connect() as connection:
        return {
            'turns': connection.execute('SELECT count(*) n FROM turns JOIN sessions USING(session_id) '
                                        'WHERE student_id=%s', (student,)).fetchone()['n'],
            'observations': connection.execute('SELECT count(*) n FROM observations WHERE student_id=%s',
                                               (student,)).fetchone()['n'],
            'mastery_history': connection.execute('SELECT count(*) n FROM mastery_history '
                'JOIN observations USING(observation_id) WHERE student_id=%s',
                (student,)).fetchone()['n'],
        }


try:
    with connect() as connection:
        migrate(connection)
        seed(connection)
    with TestClient(app) as client:
        student, headers, session = new_learner(client)
        session = at_lin003(client, headers, session)
        correct, _ = mutate(client, headers, session, 'turns',
                            steps=['2x-6=10', '2x=16', 'x=8'])
        assert correct['assessment']['assessment_status'] == 'verified_correct'
        assert correct['observation'] is not None and counts(student)['observations'] == 1
        add_case('TC01', {'problem': 'LIN-003', 'assessment': 'verified_correct',
                          'eligibility': correct['eligibility']['reason'], 'db': counts(student)})

        student, headers, session = new_learner(client)
        session = at_lin003(client, headers, session)
        wrong, _ = mutate(client, headers, session, 'turns',
                          steps=['2x-3=10', '2x=13', 'x=6.5'])
        assert wrong['assessment']['first_error_step'] == 1
        assert wrong['assessment']['diagnosis_status'] == 'suspected'
        assert 'x=8' not in wrong['message'] and 'x = 8' not in wrong['message']
        add_case('TC02', {'assessment': wrong['assessment']['assessment_status'],
                          'first_error_step': wrong['assessment']['first_error_step'],
                          'diagnosis': wrong['assessment']['diagnosis_status'],
                          'response': wrong['message'], 'db': counts(student)})
        hint, _ = mutate(client, headers, wrong['session'], 'turns',
                         action='request_hint', steps=[])
        fixed, _ = mutate(client, headers, hint['session'], 'turns',
                          steps=['x-3=5', 'x=8'])
        assert fixed['assessment']['assessment_status'] == 'verified_correct'
        assert fixed['observation'] is None and counts(student)['observations'] == 1
        add_case('TC03', {'hint_level': hint['session']['hint_level'],
                          'correction': fixed['assessment']['assessment_status'],
                          'eligibility': fixed['eligibility']['reason'], 'db': counts(student)})

        student, headers, session = new_learner(client)
        unclear, _ = mutate(client, headers, session, 'turns', steps=['x='])
        unsupported, _ = mutate(client, headers, unclear['session'], 'turns', steps=['x^2=25'])
        assert unclear['assessment']['assessment_status'] == 'needs_clarification'
        assert unsupported['assessment']['assessment_status'] == 'unverified'
        assert counts(student)['observations'] == 0
        add_case('TC04', {'unclear': unclear['assessment']['assessment_status'],
                          'outside_scope': unsupported['assessment']['reason_code'],
                          'db': counts(student)})

        student, headers, session = new_learner(client)
        first, body = mutate(client, headers, session, 'turns', steps=['x=5'])
        replay = client.post(f"/api/v1/sessions/{session['session_id']}/turns",
                             headers=headers, json=body)
        assert replay.status_code == 200 and replay.json() == first
        assert counts(student) == {'turns': 1, 'observations': 1, 'mastery_history': 1}
        add_case('TC05', {'replay_identical': True, 'db': counts(student)})

        student, headers, session = new_learner(client)
        session = at_lin003(client, headers, session)
        alternative, _ = mutate(client, headers, session, 'turns', steps=['x-3=5', 'x=8'])
        assert alternative['assessment']['assessment_status'] == 'verified_correct'
        assert alternative['observation'] is not None
        add_case('TC08', {'steps': ['x-3=5', 'x=8'],
                          'assessment': alternative['assessment']['assessment_status'],
                          'db': counts(student)})

        student, headers, session = new_learner(client)
        independent, _ = mutate(client, headers, session, 'turns', steps=['x=5'])
        session, _ = mutate(client, headers, independent['session'], 'next')
        unclear, _ = mutate(client, headers, session, 'turns', steps=['x='])
        hint, _ = mutate(client, headers, unclear['session'], 'turns',
                         action='request_hint', steps=[])
        assisted, _ = mutate(client, headers, hint['session'], 'turns', steps=['x=-4'])
        report, _ = mutate(client, headers, assisted['session'], 'finish')
        assert (report['independent_correct'], report['assisted_correct'],
                report['unverified_submissions'], report['valid_observations']) == (1, 1, 1, 1)
        add_case('TC10', {'report': {key: report[key] for key in (
            'independent_correct', 'assisted_correct', 'unverified_submissions',
            'valid_observations', 'submitted_turns')}, 'db': counts(student)})

    out = ROOT / 'docs/evidence/api-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    source_files = ('frontend/app/workspace.tsx', 'frontend/app/workspace.css',
                    'backend/app/tutor_service.py', 'backend/app/math_validator.py',
                    'content/linear_equations.v1.json', 'content/bkt.bootstrap.v1.json')
    out.write_text(json.dumps({'checked_at': datetime.now(timezone.utc).isoformat(),
        'environment': 'local FastAPI TestClient, PostgreSQL 17, isolated schema, LLM disabled',
        'versions': {'content': json.loads((ROOT / source_files[4]).read_text(encoding='utf-8'))['content_version'],
                     'validator': VALIDATOR_VERSION, 'bkt': BKT_VERSION},
        'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                          for path in source_files},
        'cases': checks}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(checks)} API/DB acceptance cases; evidence: {out}')
finally:
    os.environ.pop('PGOPTIONS', None)
    assert schema.startswith('test_phase5_') and len(schema) == 44
    with connect() as connection:
        connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
