"""Bounded recursive-descent linear grammar. Never evaluate learner Python/text."""
from fractions import Fraction as F
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from app.member2_runtime import ASSESSMENT_MODE, TASK_KINDS

VERSION = 'linear-rational-1.0.0'
EXPANSION_VERSION = 'linear-expansion-1.0.0'


class InputIssue(ValueError):
    def __init__(self, reason='ambiguous_input'):
        self.reason = reason


def normalize(text):
    return text.translate(str.maketrans({'−':'-', '×':'*', '·':'*', '÷':'/'})).strip()


class Parser:
    """Each expression is (x coefficient, constant, syntactic x presence)."""
    def __init__(self, text):
        if len(text) > 160:
            raise InputIssue('cannot_verify')
        if re.search(r'/\s*[+-]?\s*\d+(?:\.\d+)?\s*[x(]', text):
            raise InputIssue()  # 1/2x needs explicit multiplication/parentheses.
        if re.search(r'[\^<>√]|\*\*|\b[y-z]\b', text):
            raise InputIssue('unsupported_scope')
        self.tokens = []
        at = 0
        while at < len(text):
            if text[at:].isspace(): break
            m = re.match(r'\s*(\d+(?:\.\d+)?|x|[()+*/-])', text[at:])
            if not m: raise InputIssue()
            self.tokens.append(m[1]); at += m.end()
        self.at = self.nodes = 0

    def peek(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else ''

    def take(self):
        t = self.peek()
        if not t: raise InputIssue()
        self.at += 1
        return t

    def bounded(self, value):
        self.nodes += 1
        if self.nodes > 80 or any(v.numerator.bit_length() > 256 or v.denominator.bit_length() > 256 for v in value[:2]):
            raise InputIssue('cannot_verify')
        return value

    def expression(self, depth=0):
        value = self.term(depth)
        while self.peek() in ('+', '-'):
            sign = 1 if self.take() == '+' else -1
            right = self.term(depth)
            value = self.bounded((value[0]+sign*right[0], value[1]+sign*right[1], value[2] or right[2]))
        return value

    def term(self, depth):
        value = self.factor(depth)
        while self.peek() in ('*', '/', 'x', '('):
            op = self.take() if self.peek() in ('*', '/') else '*'
            right = self.factor(depth)
            if op == '/':
                if right[2]: raise InputIssue('unsupported_scope')
                if right[1] == 0: raise InputIssue()
                value = self.bounded((value[0]/right[1], value[1]/right[1], value[2]))
            else:
                if value[0] and right[0]: raise InputIssue('unsupported_scope')
                value = self.bounded((value[0]*right[1]+value[1]*right[0], value[1]*right[1], value[2] or right[2]))
        return value

    def factor(self, depth):
        if depth > 12: raise InputIssue('cannot_verify')
        sign = 1
        if self.peek() in ('+', '-'):
            sign = 1 if self.take() == '+' else -1
        token = self.take()
        if token == '(':
            value = self.expression(depth+1)
            if self.take() != ')': raise InputIssue()
        elif token == 'x': value = (F(1), F(0), True)
        elif re.fullmatch(r'\d{1,5}(?:\.\d{1,4})?', token): value = (F(0), F(token), False)
        else: raise InputIssue()
        return self.bounded((sign*value[0], sign*value[1], value[2]))

    def parse(self):
        value = self.expression()
        if self.peek(): raise InputIssue()
        return value


def equation(text):
    text = normalize(text)
    if len(text) > 160 or text.count('=') != 1: raise InputIssue()
    left, right = text.split('=')
    return Parser(left).parse(), Parser(right).parse()


def solution(eq):
    # SymPy receives only bounded rationals constructed by OUR parser, never strings.
    from sympy import Rational, Symbol, S, solveset
    left, right = eq
    a, b = left[0]-right[0], left[1]-right[1]
    x = Symbol('x', real=True)
    return solveset(Rational(a.numerator,a.denominator)*x + Rational(b.numerator,b.denominator), x, domain=S.Reals)


def isolated(eq):
    a,b = eq
    return (a[:2] == (1,0) and b[0] == 0) or (b[:2] == (1,0) and a[0] == 0)


def assessment(status, reason, **extra):
    return dict(assessment_id=str(uuid4()), assessment_status=status, first_error_step=None,
        primary_skill_id=None, error_family=None, misconception_candidate=None, diagnosis_status='unknown',
        reason_code=reason, evidence=[], verification_method='none', validator_version=VERSION, **extra)


def validate_expansion(problem, steps):
    normalized = [normalize(step) for step in steps]
    result = {'normalization': [{'raw': raw, 'normalized': value} for raw, value in zip(steps, normalized)],
              'progress': 0}

    def finish(status, reason, **fields):
        checked = assessment(status, reason)
        checked.update(validator_version=EXPANSION_VERSION, **fields)
        return {**result, 'assessment': checked}

    if not normalized or not all(normalized):
        return finish('needs_clarification', 'ambiguous_input')
    if len(normalized) > 12 or any(len(step) > 160 for step in normalized):
        return finish('unverified', 'cannot_verify')
    try:
        expected = Parser(normalize(problem['task']['expression'])).parse()[:2]
        for index, line in enumerate(normalized, 1):
            parts = line.split('=')
            values = [Parser(part.strip()).parse()[:2] for part in parts]
            if any(value != expected for value in values):
                return finish('verified_incorrect', 'invalid_transformation',
                              primary_skill_id=problem['primary_skill_id'], first_error_step=index,
                              verification_method='symbolic_and_rule', evidence=[f'step:{index}:not_equivalent'])
            result['progress'] = index
    except InputIssue as error:
        return finish('needs_clarification' if error.reason == 'ambiguous_input' else 'unverified', error.reason)

    # Each approved A02 exercise has one x term and one nonzero constant in its reduced form.
    final = re.sub(r'\s+', '', parts[-1])
    number = r'\d+(?:\.\d+)?'
    x_term = rf'(?:{number}\*?)?x'
    if re.fullmatch(rf'[+-]?(?:{x_term}[+-]{number}|{number}[+-]{x_term})', final):
        return finish('verified_correct', 'valid_solution', primary_skill_id=problem['primary_skill_id'],
                      verification_method='symbolic_and_rule', evidence=['task:verified_expansion'])
    return finish('unverified', 'valid_partial', verification_method='symbolic_and_rule',
                  evidence=['task:equivalent_but_not_reduced'])


def validate_member2_answer(problem, steps):
    from app.authoring_extended_math import check_expanded_quadratic
    from app.authoring_math import expected, response_value
    from app.curriculum import AuthoringMathTask

    def finish(status, reason, **fields):
        checked = assessment(status, reason)
        checked.update(validator_version=ASSESSMENT_MODE, **fields)
        return {'assessment': checked, 'normalization': normalization,
                'progress': 1 if status == 'verified_correct' else 0}

    normalization = []
    if len(steps) > 12 or any(len(step) > 160 for step in steps):
        return finish('unverified', 'cannot_verify')
    if not steps or not steps[-1].strip():
        return finish('needs_clarification', 'ambiguous_input')
    task = AuthoringMathTask.model_validate(problem['task'])
    if task.kind not in TASK_KINDS or problem['review']['status'] != 'human_approved':
        return finish('unverified', 'unsupported_scope')
    response = normalize(steps[-1])
    if task.kind in ('polynomial', 'factored_polynomial', 'rational_operation', 'word_equation'):
        response = re.sub(r'x\s*(?:\^\s*2|²)', 'x*x', response)
        response = re.sub(r'(?<=[0-9)])\s*(?=[x(])|(?<=x)\s*(?=\()', '*', response)
    normalization.append({'raw': steps[-1], 'normalized': response})
    target = expected(task)
    try:
        answer = response_value(task, response)
        if task.kind == 'polynomial':
            check_expanded_quadratic(response)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError):
        return finish('needs_clarification', 'ambiguous_input')
    correct = answer == target
    return finish('verified_correct' if correct else 'verified_incorrect',
                  'valid_solution' if correct else 'wrong_final_answer',
                  primary_skill_id=problem['primary_skill_id'], verification_method='symbolic_and_rule',
                  evidence=['task:final_answer_only'])


def validate(problem, steps):
    if problem.get('assessment_mode') == ASSESSMENT_MODE:
        return validate_member2_answer(problem, steps)
    task = problem.get('task')
    if task:
        if task['kind'] == 'polynomial':
            return validate_expansion(problem, steps)
        if task['kind'] != 'linear_equation':
            return {'assessment': assessment('unverified', 'unsupported_scope'), 'normalization': [], 'progress': 0}
        problem = {**problem, 'equation': task['expression'], 'common_errors': []}
    normalized = [normalize(s) for s in steps]
    result = {'assessment': assessment('unverified','cannot_verify'),
              'normalization': [{'raw':r,'normalized':n} for r,n in zip(steps,normalized)], 'progress':0}
    def finish(status, reason, **fields):
        data = assessment(status,reason); data.update(fields)
        result['assessment'] = data
        return result
    if not steps or not any(s.strip() for s in steps): return finish('needs_clarification','ambiguous_input')
    if len(steps) > 12 or any(len(s)>160 for s in steps): return finish('unverified','cannot_verify')
    try:
        original = equation(problem['equation']); expected = solution(original)
        # Only a literal repetition of the prompt is excluded from assessed numbering.
        if re.sub(r'\s','',normalized[0]) == re.sub(r'\s','',normalize(problem['equation'])):
            normalized = normalized[1:]
        last = None
        for index, step in enumerate(normalized, 1):
            parsed = equation(step)
            if solution(parsed) != expected:
                single_final = len(normalized) == 1 and isolated(parsed)
                data = dict(primary_skill_id=problem['primary_skill_id'], verification_method='symbolic_and_rule',
                    first_error_step=None if single_final else index, evidence=[f'step:{index}:not_equivalent'])
                # Only a matching authored ERROR TRACE suggests a diagnosis; final guesses do not.
                if not single_final:
                    for error in problem['common_errors']:
                        if error['first_error_step'] == index and re.sub(r'\s','',step) == re.sub(r'\s','',normalize(error['steps'][index-1])):
                            data.update(error_family=error['error_id'], misconception_candidate=error['hypothesis'], diagnosis_status='suspected')
                            break
                return finish('verified_incorrect','wrong_final_answer' if single_final else 'invalid_transformation',**data)
            result['progress'] = index
            last = parsed
        if last and isolated(last):
            return finish('verified_correct','valid_solution',primary_skill_id=problem['primary_skill_id'],
                          verification_method='symbolic_and_rule',evidence=['task:verified_solution'])
        return finish('unverified','valid_partial',verification_method='symbolic_and_rule',evidence=['task:valid_partial'])
    except InputIssue as e:
        return finish('needs_clarification' if e.reason == 'ambiguous_input' else 'unverified', e.reason)


def validate_bounded(problem, steps, *, timeout=None):
    """Kill/reap the worker on timeout; no lingering timed-out executor threads."""
    limit = timeout if timeout is not None else min(3.0,max(.05,float(os.getenv('VALIDATOR_TIMEOUT_SECONDS','3'))))
    try:
        completed = subprocess.run([sys.executable, '-m', 'app.math_worker'],
            input=json.dumps({'problem':problem,'steps':steps}), capture_output=True, text=True,
            encoding='utf-8', timeout=limit, cwd=Path(__file__).resolve().parents[1])
        if completed.returncode: raise ValueError('worker_failure')
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {'assessment':assessment('unverified','cannot_verify'), 'normalization':[], 'progress':0, 'worker_status':'timeout'}
    except (ValueError,OSError):
        return {'assessment':assessment('unverified','cannot_verify'), 'normalization':[], 'progress':0, 'worker_status':'worker_failure'}
