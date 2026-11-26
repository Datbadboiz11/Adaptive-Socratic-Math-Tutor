"""Approved content, bounded grading, and PostgreSQL session acceptance for Member 2."""
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.curriculum import PilotBank
from app.db import connect
from app.main import app
from app.manage import migrate, seed
from app.math_validator import validate
from app.member2_runtime import ASSESSMENT_MODE, RELEASE, demo_catalog, seed_member2


PACKS = PilotBank.model_validate_json((RELEASE / 'approved-bank.json').read_bytes()).packs


@pytest.mark.parametrize('pack', PACKS, ids=lambda pack: pack.concept_id)
def test_all_78_approved_answers_and_authored_errors(pack):
    errors = {error.problem_id: error for error in pack.errors}
    for problem in pack.problems:
        item = demo_catalog()[(problem.case_id, pack.content_version)]
        assert set(item.public).isdisjoint({'reference_answer', 'hint_ladder', 'reference_steps', 'source_group', 'review'})
        assert item.public['concept_id'] == pack.concept_id
        result = validate(item.private, ['First line is saved for the journal.', problem.reference_answer])['assessment']
        assert result['assessment_status'] == 'verified_correct', (problem.case_id, result)
        assert result['primary_skill_id'] == problem.primary_skill_id
        assert result['validator_version'] == ASSESSMENT_MODE and result['first_error_step'] is None
        assert result['evidence'] == ['task:final_answer_only']
        if problem.case_id in errors:
            wrong = validate(item.private, errors[problem.case_id].response_steps)['assessment']
            assert wrong['assessment_status'] == 'verified_incorrect', (problem.case_id, wrong)
            assert wrong['first_error_step'] is None and wrong['diagnosis_status'] == 'unknown'
        malformed = validate(item.private, ['?'])['assessment']
        assert malformed['assessment_status'] == 'needs_clarification'


def test_expansion_accepts_common_notation_but_requires_expanded_form():
    pack = next(pack for pack in PACKS if pack.concept_id == 'A04')
    problem = pack.problems[0]
    private = demo_catalog()[(problem.case_id, pack.content_version)].private
    assert validate(private, ['12x² − 28x'])['assessment']['assessment_status'] == 'verified_correct'
    assert validate(private, [problem.task.expression])['assessment']['assessment_status'] == 'needs_clarification'


@pytest.fixture(scope='module')
def database():
    if not os.getenv('RUN_DB_TESTS'):
        pytest.skip('PostgreSQL integration requires RUN_DB_TESTS=1')
    schema = 'test_member2_' + uuid4().hex
    with connect() as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    with pytest.MonkeyPatch.context() as env:
        env.setenv('PGOPTIONS', '-c search_path=' + schema)
        env.setenv('DEMO_MODE', 'true')
        env.setenv('TUTOR_ENABLED', 'true')
        env.setenv('LLM_ENABLED', 'false')
        env.setenv('VALIDATOR_TIMEOUT_SECONDS', '3')
        try:
            with connect() as connection:
                migrate(connection)
                seed(connection)
                assert seed_member2(connection) == {'topics': 13, 'problems': 78, 'inserted': 78}
                assert seed_member2(connection)['inserted'] == 0
            yield
        finally:
            assert schema.startswith('test_member2_') and len(schema) == 45
            with connect() as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@pytest.fixture
def learner(database):
    student = 'M2-TEST-' + uuid4().hex
    with connect() as connection:
        connection.execute('INSERT INTO profiles(student_id,display_name) VALUES (%s,%s)', (student, 'Synthetic Member 2 test'))
    with TestClient(app) as client:
        login = client.post('/api/v1/demo/login', json={'demo_profile_id': student})
        yield client, {'Authorization': 'Bearer ' + login.json()['access_token']}, student


def start(learner, concept_id):
    client, headers, student = learner
    response = client.post('/api/v1/sessions', headers=headers, json={
        'request_id': str(uuid4()), 'demo_profile_id': student, 'topic_id': 'TOPIC-' + concept_id})
    assert response.status_code == 201, response.text
    return response.json()


def mutate(learner, session, endpoint, **payload):
    client, headers, _ = learner
    body = {'request_id': str(uuid4()), 'expected_state_version': session['state_version'], **payload}
    method = 'PUT' if endpoint == 'draft' else 'POST'
    url = f"/api/v1/sessions/{session['session_id']}/{endpoint}"
    response = client.request(method, url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def submit(learner, session, steps, action='submit'):
    return mutate(learner, session, 'turns', action=action, steps=steps,
                  opportunity_id=session['current_opportunity_id'])


@pytest.mark.parametrize('pack', PACKS, ids=lambda pack: pack.concept_id)
def test_every_approved_topic_has_full_working_session(learner, pack):
    client, headers, _ = learner
    available = client.get('/api/v1/topics', headers=headers).json()
    assert {row['topic_id'] for row in available if row['tutoring_ready']} == {'TOPIC-' + p.concept_id for p in PACKS}
    session = start(learner, pack.concept_id)
    assert session['tutoring_enabled'] and session['review_status'] == 'human_approved'
    assert session['problem']['task']['kind'] == pack.problems[0].task.kind
    assert 'equation' not in session['problem'] and 'reference_answer' not in session['problem']
    hinted, _ = submit(learner, session, [], 'request_hint')
    assert hinted['message'] == pack.hints[0].text and hinted['response_source'] == 'reviewed_hint'
    assert hinted['session']['hint_level'] == 1 and hinted['observation'] is None
    solved, body = submit(learner, hinted['session'], [pack.problems[0].reference_answer])
    assert solved['assessment']['assessment_status'] == 'verified_correct' and solved['observation'] is None
    replay = client.post(f"/api/v1/sessions/{session['session_id']}/turns", headers=headers, json=body)
    assert replay.json() == solved
    report, _ = mutate(learner, solved['session'], 'finish')
    assert report['assessment_scope'] == 'final_answer'
    assert (report['independent_correct'], report['assisted_correct'], report['valid_observations']) == (0, 1, 0)
    assert not report['mastery']


def test_policy_ladder_pause_and_report_without_model_or_false_mastery(learner, monkeypatch):
    from app import tutor

    def reject_external(*args, **kwargs):
        raise AssertionError('Reviewed demo policy must not contact a model')

    monkeypatch.setenv('LLM_ENABLED', 'true')
    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-token')
    monkeypatch.setenv('GEMINI_MODEL', 'synthetic-test-model')
    monkeypatch.setattr('app.gemini_wording.select_wording', reject_external)
    assert tutor.MEMBER2_POLICY_VERSION == 'member2-reviewed-hints-1.0.0'

    pack = next(pack for pack in PACKS if pack.concept_id == 'N02')
    session = start(learner, pack.concept_id)
    invalid, _ = submit(learner, session, ['?'])
    assert invalid['assessment']['assessment_status'] == 'needs_clarification'
    assert invalid['session']['hint_level'] == 0
    wrong, _ = submit(learner, invalid['session'], [pack.errors[0].response_steps[0]])
    assert wrong['assessment']['assessment_status'] == 'verified_incorrect'
    assert wrong['message'] == pack.hints[0].text
    assert pack.problems[0].reference_answer not in wrong['message']
    session = wrong['session']
    for level in (2, 3):
        hinted, _ = submit(learner, session, [], 'request_hint')
        assert hinted['message'] == pack.hints[level - 1].text
        assert hinted['tutor']['policy_version'] == tutor.MEMBER2_POLICY_VERSION
        session = hinted['session']
        assert session['hint_level'] == level
    capped, _ = submit(learner, session, [], 'request_hint')
    assert capped['session']['hint_level'] == 3 and capped['tutor']['action'] == 'offer_pause'
    paused, _ = mutate(learner, capped['session'], 'pause')
    resumed, _ = mutate(learner, paused, 'resume')
    assert resumed['draft'] == wrong['session']['draft'] and resumed['hint_level'] == 3
    fixed, _ = submit(learner, resumed, [pack.problems[0].reference_answer])
    near, _ = mutate(learner, fixed['session'], 'next')
    assert near['relation'] == 'near_practice'
    fixed_near, _ = submit(learner, near, [pack.problems[1].reference_answer])
    independent, _ = mutate(learner, fixed_near['session'], 'next')
    fixed_independent, _ = submit(learner, independent, [pack.problems[2].reference_answer])
    report, _ = mutate(learner, fixed_independent['session'], 'finish')
    assert (report['independent_correct'], report['assisted_correct'], report['repeat_or_near_correct']) == (1, 1, 1)
    assert report['valid_observations'] == 0 and report['mastery'] == []


def test_new_approved_topics_close_when_validator_is_disabled(learner, monkeypatch):
    client, headers, student = learner
    monkeypatch.setenv('TUTOR_ENABLED', 'false')
    available = client.get('/api/v1/topics', headers=headers).json()
    assert not any(topic['tutoring_ready'] for topic in available)
    response = client.post('/api/v1/sessions', headers=headers, json={
        'request_id': str(uuid4()), 'demo_profile_id': student, 'topic_id': 'TOPIC-A10'})
    assert response.status_code == 409 and response.json()['code'] == 'content_not_ready'
