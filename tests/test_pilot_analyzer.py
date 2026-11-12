"""Learner math semantics, abstention, diagnosis boundaries and preview API."""
from fractions import Fraction
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.curriculum import load_curriculum
from app.learner_math import expression
from app.main import app
from app.math_validator import InputIssue
from app.pilot_analyzer import analyze, analyze_bounded
from app.pilot_contracts import PilotSubmission
from app.sessions import principal

REGISTRY, BANK = load_curriculum()
PROBLEMS = {p.case_id: p for pack in BANK.packs for p in pack.problems}
ERRORS = {pack.concept_id: pack.errors for pack in BANK.packs}


def grade(problem_id, steps, kind='steps'):
    problem = PROBLEMS[problem_id]
    return analyze(problem, PilotSubmission(submission_kind=kind, steps=steps), ERRORS[problem.concept_id])


@pytest.mark.parametrize('problem', list(PROBLEMS.values()), ids=lambda p: p.case_id)
def test_all_pilot_reference_traces_pass_learner_checker(problem):
    result = grade(problem.case_id, problem.reference_steps)
    assert result.assessment.assessment_status == 'verified_correct'
    assert result.completed and not result.updates_student_model
    assert result.assessment.misconception_candidate is None


@pytest.mark.parametrize('error', [e for errors in ERRORS.values() for e in errors], ids=lambda e: e.error_id)
def test_first_error_and_authored_hypothesis_are_suspected_only(error):
    result = grade(error.problem_id, error.response_steps)
    assert result.assessment.assessment_status == 'verified_incorrect'
    assert result.assessment.first_error_step == error.first_error_step
    assert result.assessment.error_family == error.family
    assert result.assessment.misconception_candidate == error.error_id
    assert result.assessment.diagnosis_status == 'suspected'
    assert result.diagnostic_question == error.diagnostic_question
    assert all(s.status == 'not_assessed' for s in result.step_checks[error.first_error_step:])


@pytest.mark.parametrize('problem_id,steps', [
    ('P-A02-01', ['3(x+2)=6+3x']),
    ('P-A03-01', ['2x+3x', '5x']),
    ('P-A03-03', ['4x+2x-1+3', '2+6x']),
    ('P-A01-01', ['2x+3=2*(-2)+3', '-1']),
    ('P-E02-03', ['2(x-3)=10', 'x-3=5', '8=x']),
    ('P-N01-01', ['−7+4=−3']),
    ('P-N02-01', ['−6×4=−24']),
    ('P-N04-01', ['6/8=3/4']),
    ('P-F05-01', ['(2, -3)']),
])
def test_alternative_solutions_and_unicode(problem_id, steps):
    assert grade(problem_id, steps).completed


@pytest.mark.parametrize('problem_id,steps', [
    ('P-A02-01', ['3(x+2)']),
    ('P-A02-01', ['3x+3*2']),
    ('P-A03-01', ['2x+3x']),
    ('P-A01-01', ['2*(-2)+3']),
    ('P-E02-03', ['x-3=5']),
    ('P-N04-01', ['6/8']),
    ('P-N04-01', ['0.75']),
    ('P-N04-03', ['2/(-3)']),
    ('P-F05-01', ['(4/2,4-8+1)']),
])
def test_equivalent_but_unfinished_forms_are_not_correct_observations(problem_id, steps):
    result = grade(problem_id, steps)
    assert result.assessment.reason_code == 'valid_partial'
    assert not result.completed and result.assessment.primary_skill_id is None


@pytest.mark.parametrize('answer', ['6.5', 'x=6.5'])
def test_wrong_final_answer_does_not_invent_step_or_misconception(answer):
    result = grade('P-E02-03', [answer], 'final_answer')
    assert result.assessment.assessment_status == 'verified_incorrect'
    assert result.assessment.reason_code == 'wrong_final_answer'
    assert result.assessment.first_error_step is None
    assert result.assessment.misconception_candidate is None and result.diagnostic_question is None


def test_verified_error_before_malformed_suffix_is_retained_without_parsing_suffix():
    result = grade('P-E02-03', ['2x-3=10', 'giải thích bằng lời'])
    assert result.assessment.first_error_step == 1
    assert result.step_checks[1].status == 'not_assessed'
    assert result.assessment.error_family == 'distribution_missing_term'


def test_uncertainty_before_later_wrong_step_prevents_claiming_first_error():
    result = grade('P-E02-03', ['giải thích bằng lời', '2x-3=10'])
    assert result.assessment.assessment_status == 'needs_clarification'
    assert result.assessment.first_error_step is None


def test_unknown_wrong_step_and_wrong_root_matching_do_not_force_diagnosis():
    assert grade('P-A02-01', ['3x+100']).assessment.diagnosis_status == 'unknown'
    # Same erroneous root as an authored trace, completely different equation.
    assert grade('P-E02-03', ['4x=26']).assessment.misconception_candidate is None
    assert grade('P-N01-01', ['8+3']).assessment.misconception_candidate is None


def test_polynomial_hypothesis_accepts_reordered_equivalent_error_pattern():
    assert grade('P-A02-01', ['2+3x']).assessment.error_family == 'distribution_missing_term'


@pytest.mark.parametrize('text,reason', [
    ('1/2x', 'ambiguous_input'), ('3x+', 'ambiguous_input'),
    ('x/0', 'ambiguous_input'), ('x/(x-x+1)', 'unsupported_scope'),
    ('x^3', 'unsupported_scope'), ('x*x*x', 'unsupported_scope'),
    ('__import__("os").system("calc")', 'ambiguous_input'),
    ('sqrt(4)', 'ambiguous_input'), ('y+1', 'unsupported_scope'),
    ('1e100', 'ambiguous_input'), ('999999', 'ambiguous_input'),
    ('('*14+'x'+')'*14, 'cannot_verify'),
])
def test_unsupported_ambiguous_and_malicious_input_abstain(text, reason):
    result = grade('P-A02-01', [text])
    assert result.assessment.assessment_status in ('unverified', 'needs_clarification')
    assert result.assessment.reason_code == reason
    assert result.assessment.first_error_step is None


def test_exact_polynomial_values_not_sampled_equality():
    assert expression('0.1x+0.2x').coefficients == (0, Fraction(3, 10), 0)
    assert expression('x^2-2x+1').coefficients == (1, -2, 1)
    assert not grade('P-A02-01', ['x*x+3x+6']).completed
    for coefficient in range(-5, 6):
        if not coefficient:
            continue
        base = PROBLEMS['P-A02-01']
        problem = base.model_copy(update={'task': base.task.model_copy(update={'expression': f'{coefficient}*(x+2)'})})
        submission = PilotSubmission(submission_kind='steps', steps=[f'{2*coefficient}{coefficient:+}x'])
        assert analyze(problem, submission).completed


def test_reverse_distribution_requires_factored_form():
    assert grade('P-A02-05', ['(x+3)*5']).completed
    assert grade('P-A02-05', ['5x+15']).assessment.reason_code == 'valid_partial'
    assert grade('P-A02-05', ['1*(5x+15)']).assessment.reason_code == 'valid_partial'


def test_unique_equation_vs_all_real_and_empty_sets():
    for line in ['0=0', '0=1']:
        assert grade('P-E02-03', [line]).assessment.assessment_status == 'verified_incorrect'


def test_e01_scalar_does_not_measure_transformation_skill():
    assert grade('P-E01-01', ['4'], 'final_answer').assessment.reason_code == 'valid_partial'
    assert grade('P-E01-01', ['4']).assessment.reason_code == 'valid_partial'
    assert grade('P-E01-01', ['2x=8', 'x=4']).completed
    assert grade('P-E01-01', ['5'], 'final_answer').assessment.primary_skill_id is None


def test_task_semantics_do_not_depend_on_private_reference_answer():
    base = PROBLEMS['P-A02-01']
    problem = base.model_copy(update={'reference_answer': '999'})
    result = analyze(problem, PilotSubmission(submission_kind='steps', steps=['3x+6']))
    assert result.completed


def test_worker_success_and_timeout():
    problem = PROBLEMS['P-A02-01']
    submission = PilotSubmission(submission_kind='steps', steps=['3x+6'])
    outcome = analyze_bounded(problem, submission, timeout=3, content_version='future-version')
    assert outcome.completed and outcome.content_version == 'future-version'
    assert analyze_bounded(problem, submission, timeout=.001).assessment.reason_code == 'cannot_verify'


@pytest.mark.parametrize('limit', ['broken', 'nan', 'inf', '0', '-1'])
def test_invalid_worker_deadline_abstains_instead_of_crashing(monkeypatch, limit):
    monkeypatch.setenv('VALIDATOR_TIMEOUT_SECONDS', limit)
    result = analyze_bounded(PROBLEMS['P-A02-01'], PilotSubmission(submission_kind='steps', steps=['3x+6']))
    assert result.assessment.reason_code == 'cannot_verify'


def test_submission_limits_and_explicit_final_answer_intent():
    with pytest.raises(ValidationError): PilotSubmission(submission_kind='steps', steps=['x'*161])
    with pytest.raises(ValidationError): PilotSubmission(submission_kind='steps', steps=[])
    assert grade('P-A02-01', ['3x+6', '3x+6'], 'final_answer').assessment.assessment_status == 'needs_clarification'


@pytest.fixture
def preview_client(monkeypatch):
    if os.getenv('SKIP_ASGI_TESTS') == '1':
        pytest.skip('Local sandbox cannot initialize asyncio socketpair; run HTTP tests in CI')
    monkeypatch.setenv('DEMO_MODE', 'true')
    monkeypatch.setenv('PILOT_ANALYZER_ENABLED', 'true')
    app.dependency_overrides[principal] = lambda: 'synthetic-internal-reviewer'
    yield TestClient(app)
    app.dependency_overrides.pop(principal, None)


def test_preview_opt_in_and_unknown_problem(preview_client, monkeypatch):
    monkeypatch.setenv('PILOT_ANALYZER_ENABLED', 'false')
    assert preview_client.get('/api/v1/pilot/concepts').status_code == 403
    monkeypatch.setenv('PILOT_ANALYZER_ENABLED', 'true')
    assert preview_client.get('/api/v1/pilot/problems/missing').status_code == 404


def test_preview_public_projection_and_actual_worker(preview_client):
    response = preview_client.get('/api/v1/pilot/concepts')
    assert response.status_code == 200
    concepts = response.json()
    assert len(concepts) == 10 and sum(len(c['problems']) for c in concepts) == 60
    assert all(c['review_status'] == 'draft' for c in concepts)
    assert not any(key in response.text for key in ['reference_answer', 'reference_steps', 'diagnostic_question', 'errors'])
    response = preview_client.post('/api/v1/pilot/problems/P-A02-01/assess',
        json={'submission_kind': 'steps', 'steps': ['3x+2']})
    assert response.status_code == 200
    assert response.json()['assessment']['error_family'] == 'distribution_missing_term'
    assert response.json()['updates_student_model'] is False
    assert preview_client.post('/api/v1/pilot/problems/P-A02-01/assess',
        json={'submission_kind': 'steps', 'steps': ['3x+6'], 'reference_answer': '999'}).status_code == 422


def test_preview_authentication_is_not_bypassed(monkeypatch):
    if os.getenv('SKIP_ASGI_TESTS') == '1':
        pytest.skip('Local sandbox cannot initialize asyncio socketpair; run HTTP tests in CI')
    monkeypatch.setenv('DEMO_MODE', 'true')
    monkeypatch.setenv('PILOT_ANALYZER_ENABLED', 'true')
    assert TestClient(app).get('/api/v1/pilot/concepts').status_code == 401


def test_preview_handler_projection_and_gate_without_network(monkeypatch):
    from app.pilot_api import concepts, public_problem, require_preview
    from app.sessions import ApiError
    monkeypatch.setenv('PILOT_ANALYZER_ENABLED', 'false')
    with pytest.raises(ApiError) as failure: require_preview(student='test-reviewer')
    assert failure.value.status == 403
    monkeypatch.setenv('PILOT_ANALYZER_ENABLED', 'true')
    assert require_preview(student='test-reviewer') == 'test-reviewer'
    assert len(concepts(student='test-reviewer')) == 10
    pack = BANK.packs[1]
    projection = public_problem(pack, pack.problems[0]).model_dump()
    assert 'reference_answer' not in projection and 'errors' not in projection


def test_authentication_dependency_requires_demo_and_token_without_network(monkeypatch):
    from app.sessions import ApiError
    monkeypatch.setenv('DEMO_MODE', 'false')
    with pytest.raises(ApiError) as failure: principal(authorization=None)
    assert failure.value.status == 403
    monkeypatch.setenv('DEMO_MODE', 'true')
    with pytest.raises(ApiError) as failure: principal(authorization=None)
    assert failure.value.status == 401


def test_dev_corpus_reproduces_labels_and_source_groups():
    sys.path.insert(0, str(ROOT))
    from research.analyzer.evaluate import build, evaluate, DevBank, DATASET
    saved = DevBank.model_validate_json(DATASET.read_text(encoding='utf-8'))
    assert saved == build()
    report, predictions = evaluate()
    assert report['records'] == 180 and report['exact_matches'] == 180
    assert not report['failures'] and len(predictions) == 180
    assert saved.split == 'authoring_dev' and saved.label_status != 'human_approved'
