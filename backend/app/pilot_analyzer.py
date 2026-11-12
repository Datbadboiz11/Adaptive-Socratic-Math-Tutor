"""Verified first-error analysis with conservative authored-pattern hypotheses."""
import json
from functools import partial
import math
import os
from pathlib import Path
import subprocess
import sys

from app.authoring_math import expected
from app.contracts import Assessment
from app.curriculum import AuthoredProblem
from app.learner_math import compact, expression, value_and_completion
from app.math_validator import InputIssue, assessment
from app.pilot_contracts import PilotAnalysis, PilotSubmission, StepCheck

VERSION = 'pilot-learner-1.0.0'
LIMITATIONS = [
    'Nội dung và mẫu lỗi đang ở trạng thái nháp; chỉ thử nội bộ.',
    'Chấm các biểu thức/phương trình đầy đủ trong phạm vi pilot, chưa chấm lời giải tự do bằng lời.',
    'Giả thuyết từ mẫu lỗi chỉ là suspected; chưa chứng minh misconception bền vững.',
    'Không lưu phiên học hoặc cập nhật BKT từ API thử authoring này.',
]


def result(problem, submission, status, reason, *, content_version, checks=(), completed=False, fields=None, question=None):
    data = assessment(status, reason)
    data.update(validator_version=VERSION)
    data.update(fields or {})
    return PilotAnalysis(problem_id=problem.case_id, concept_id=problem.concept_id,
        content_version=content_version,
        submission_kind=submission.submission_kind, assessment=Assessment.model_validate(data),
        step_checks=list(checks), completed=completed, diagnostic_question=question,
        diagnostic_source='authored_pattern' if question else 'none', limitations=LIMITATIONS)


def target_value(problem):
    value = expected(problem.task)
    return ('unique', value) if problem.task.kind == 'linear_equation' else value


def matches_target(problem, value):
    target = target_value(problem)
    if problem.task.kind in ('linear_equation', 'quadratic_vertex'):
        return value == target
    return all(segment == target for segment in value)


def equivalent_pattern(problem, actual, authored):
    # Numerical equality alone cannot explain a student's thought process.
    if problem.task.kind in ('numeric', 'evaluate', 'quadratic_vertex'):
        return compact(actual) == compact(authored)
    if problem.task.kind == 'linear_equation':
        # Same wrong root is NOT evidence of the same faulty transformation.
        if actual.count('=') != 1 or authored.count('=') != 1:
            return False
        try:
            a = tuple(expression(s).coefficients for s in actual.split('='))
            b = tuple(expression(s).coefficients for s in authored.split('='))
            return a == b or a == tuple(reversed(b))
        except InputIssue:
            return False
    try:
        a, _ = value_and_completion(problem, actual)
        b, _ = value_and_completion(problem, authored)
        return a == b
    except InputIssue:
        return False


def analyze(problem: AuthoredProblem, submission: PilotSubmission, errors=(), *, content_version='0.1.0'):
    respond = partial(result, content_version=content_version)
    normalized = list(submission.steps)
    if submission.submission_kind == 'final_answer' and len(normalized) != 1:
        return respond(problem, submission, 'needs_clarification', 'ambiguous_input')
    # A literal copy of the task is context, not a learner step.
    if submission.submission_kind == 'steps' and len(normalized) > 1 and compact(normalized[0]) == compact(problem.task.expression):
        normalized = normalized[1:]
    if not normalized or all(compact(s) == compact(problem.task.expression) for s in normalized):
        # A constant function can legitimately have the same scalar as its task.
        if not (problem.task.kind == 'evaluate' and 'x' not in problem.task.expression):
            return respond(problem, submission, 'unverified', 'valid_partial')
    checks = []
    for index, step in enumerate(normalized, 1):
        try:
            value, complete = value_and_completion(problem, step)
        except InputIssue as error:
            checks.extend([StepCheck(step=index, status='unverified'),
                           *[StepCheck(step=i, status='not_assessed') for i in range(index+1, len(normalized)+1)]])
            return respond(problem, submission, 'needs_clarification' if error.reason == 'ambiguous_input' else 'unverified',
                          error.reason, checks=checks)
        if not matches_target(problem, value):
            checks.extend([StepCheck(step=index, status='incorrect'),
                           *[StepCheck(step=i, status='not_assessed') for i in range(index+1, len(normalized)+1)]])
            final_only = submission.submission_kind == 'final_answer'
            fields = {'primary_skill_id': None if final_only and problem.concept_id == 'E01' else problem.primary_skill_id,
                      'verification_method': 'symbolic_and_rule',
                      'evidence': [f'step:{index}:not_equivalent'],
                      'first_error_step': None if final_only else index}
            question = None
            if not final_only:
                for error in errors:
                    if (error.problem_id == problem.case_id and error.first_error_step == index and
                        equivalent_pattern(problem, step, error.response_steps[index-1])):
                        fields.update(error_family=error.family, misconception_candidate=error.error_id,
                                      diagnosis_status='suspected')
                        fields['evidence'].append(f'authoring_error:{error.error_id}')
                        question = error.diagnostic_question
                        break
            return respond(problem, submission, 'verified_incorrect',
                          'wrong_final_answer' if final_only else 'invalid_transformation',
                          fields=fields, checks=checks, question=question)
        checks.append(StepCheck(step=index, status='equivalent'))
    # E01 measures transformations: a scalar final answer gives no step evidence.
    if problem.concept_id == 'E01' and (submission.submission_kind == 'final_answer' or not any('=' in s for s in normalized)):
        complete = False
    if not complete:
        return respond(problem, submission, 'unverified', 'valid_partial', checks=checks,
                      fields={'verification_method': 'symbolic_and_rule', 'evidence': ['task:valid_partial']})
    return respond(problem, submission, 'verified_correct', 'valid_solution', checks=checks, completed=True,
                  fields={'primary_skill_id': problem.primary_skill_id, 'verification_method': 'symbolic_and_rule',
                          'evidence': ['task:verified_solution']})


def analyze_bounded(problem, submission, errors=(), *, timeout=None, content_version='0.1.0'):
    """Process deadline bounds learner parsing; no paid API calls or DB writes."""
    try:
        limit = float(timeout if timeout is not None else os.getenv('VALIDATOR_TIMEOUT_SECONDS', '3'))
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError('invalid_deadline')
        limit = min(3.0, limit)
        completed = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'app.pilot_worker'],
            input=json.dumps({'problem': problem.model_dump(mode='json'),
                              'submission': submission.model_dump(mode='json'),
                              'errors': [e.model_dump(mode='json') for e in errors],
                              'content_version': content_version}),
            capture_output=True, text=True, encoding='utf-8', timeout=limit,
            cwd=Path(__file__).resolve().parents[1])
        if completed.returncode:
            raise ValueError('worker_failure')
        return PilotAnalysis.model_validate_json(completed.stdout)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return result(problem, submission, 'unverified', 'cannot_verify', content_version=content_version)
