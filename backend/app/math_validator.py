"""Bounded symbolic math checks built only from a small learner-input grammar.

Learner text is never passed to eval/exec or to SymPy's string parsers.  The
recursive-descent parser below constructs SymPy objects only from recognized
numbers, variables, bounded constant square roots, and arithmetic operators.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from app.member2_runtime import ASSESSMENT_MODE, TASK_KINDS

VERSION = 'symbolic-bounded-2.2.0'
MAX_TEXT = 160
MAX_STEPS = 12
MAX_NODES = 80
EXPANSION_VERSION = 'linear-expansion-1.0.0'


class InputIssue(ValueError):
    def __init__(self, reason='ambiguous_input'):
        self.reason = reason


def normalize(text):
    text = str(text)
    for malformed, replacement in (
        ('âˆ’', '-'),
        ('Ã—', '*'),
        ('Â·', '*'),
        ('Ã·', '/'),
        ('≠', '!='),
        ('âˆš', 'sqrt'),
        ('√', 'sqrt'),
    ):
        text = text.replace(malformed, replacement)
    return text.translate(str.maketrans({'−': '-', '×': '*', '·': '*', '÷': '/'})).strip()


class ParsedExpression:
    def __init__(self, expr, exclusions=(), variables=()):
        self.expr = expr
        self.exclusions = tuple(exclusions)
        self.variables = frozenset(variables)


class Parser:
    """Small arithmetic grammar producing exact, bounded SymPy expressions."""

    def __init__(self, text):
        import sympy as sp

        self.sp = sp
        self.symbols = {'x': sp.Symbol('x', real=True), 'y': sp.Symbol('y', real=True)}
        self.text = normalize(text)
        if len(self.text) > MAX_TEXT:
            raise InputIssue('cannot_verify')
        # Keep the historical ambiguity guard for an unparenthesized 1/2x.
        if re.search(r'/\s*\d+(?:\.\d+)?\s*[xy(]', self.text):
            raise InputIssue()
        if re.search(r'\*\*|[<>]|\\', self.text):
            raise InputIssue('unsupported_scope')
        if re.search(r'[^0-9A-Za-z_\s()+*/^,.-]', self.text):
            raise InputIssue()
        self.tokens = []
        at = 0
        token_re = re.compile(r'\s*(\d+(?:\.\d+)?|[A-Za-z_]+|[()+*/^,-])')
        while at < len(self.text):
            match = token_re.match(self.text, at)
            if not match:
                raise InputIssue()
            token = match.group(1)
            self.tokens.append(token)
            at = match.end()
        if len(self.tokens) > MAX_NODES:
            raise InputIssue('cannot_verify')
        self.at = 0
        self.nodes = 0

    def peek(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else ''

    def take(self):
        token = self.peek()
        if not token:
            raise InputIssue()
        self.at += 1
        return token

    def bounded(self, expr, exclusions=(), variables=()):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise InputIssue('cannot_verify')
        sp = self.sp
        try:
            if sp.count_ops(expr) > 120:
                raise InputIssue('cannot_verify')
            numerator, denominator = sp.together(expr).as_numer_denom()
            for part in (numerator, denominator):
                poly = sp.Poly(part, *tuple(self.symbols.values()))
                if poly.total_degree() > 2:
                    raise InputIssue('unsupported_scope')
                for coefficient in poly.coeffs():
                    if coefficient.is_Rational:
                        q = sp.Rational(coefficient)
                        if max(abs(int(q.p)).bit_length(), int(q.q).bit_length()) > 256:
                            raise InputIssue('cannot_verify')
        except InputIssue:
            raise
        except Exception as exc:
            raise InputIssue('unsupported_scope') from exc
        return ParsedExpression(expr, exclusions, variables)

    def expression(self, depth=0):
        value = self.term(depth)
        while self.peek() in ('+', '-'):
            op = self.take()
            right = self.term(depth)
            sign = 1 if op == '+' else -1
            value = self.bounded(
                value.expr + sign * right.expr,
                value.exclusions + right.exclusions,
                value.variables | right.variables,
            )
        return value

    def term(self, depth):
        value = self.factor(depth)
        while True:
            if self.peek() in ('*', '/'):
                op = self.take()
                right = self.factor(depth)
            elif (
                self.peek() in ('x', 'y', '(', 'sqrt')
                or re.fullmatch(r'\d+(?:\.\d+)?', self.peek())
            ):
                # Conventional implicit multiplication: 2x, 2sqrt(3), (x+1)(x-1).
                op = '*'
                right = self.factor(depth)
            else:
                break
            exclusions = value.exclusions + right.exclusions
            if op == '/':
                if right.expr == 0:
                    raise InputIssue()
                denominator_num = self.sp.together(right.expr).as_numer_denom()[0]
                exclusions += (denominator_num,)
                expr = value.expr / right.expr
            else:
                expr = value.expr * right.expr
            value = self.bounded(expr, exclusions, value.variables | right.variables)
        return value

    def factor(self, depth):
        if depth > 12:
            raise InputIssue('cannot_verify')
        sign = 1
        if self.peek() in ('+', '-'):
            sign = 1 if self.take() == '+' else -1
        token = self.take()
        if token == '(':
            value = self.expression(depth + 1)
            if self.take() != ')':
                raise InputIssue()
        elif token == 'sqrt':
            # Allow bounded constant square roots (e.g., sqrt(2) or √2) for E06 quadratic roots.
            if self.peek() == '(':
                self.take()
                inner = self.expression(depth + 1)
                if self.take() != ')':
                    raise InputIssue()
            elif re.fullmatch(r'\d{1,5}(?:\.\d{1,4})?', self.peek()):
                inner = self.bounded(self.sp.Rational(self.take()))
            else:
                raise InputIssue('unsupported_scope')
            if inner.variables or inner.expr.free_symbols:
                raise InputIssue('unsupported_scope')
            if inner.expr < 0:
                raise InputIssue('unsupported_scope')
            value = self.bounded(self.sp.sqrt(inner.expr), inner.exclusions)
        elif token in self.symbols:
            value = self.bounded(self.symbols[token], variables=(token,))
        elif re.fullmatch(r'\d{1,5}(?:\.\d{1,4})?', token):
            value = self.bounded(self.sp.Rational(token))
        elif token.isascii() and token.isalpha() and len(token) == 1:
            raise InputIssue('unsupported_scope')
        else:
            raise InputIssue()
        expr = value.expr
        if self.peek() == '^':
            self.take()
            exponent = self.take()
            if exponent not in ('0', '1', '2'):
                raise InputIssue('unsupported_scope')
            expr = expr ** int(exponent)
        return self.bounded(sign * expr, value.exclusions, value.variables)

    def parse(self):
        value = self.expression()
        if self.peek():
            raise InputIssue()
        return value


def split_rows(text):
    """Split a system written as separate lines, semicolon rows, or equations."""
    if isinstance(text, (list, tuple)):
        rows = [str(row).strip() for row in text]
    elif isinstance(text, str):
        rows = [row.strip() for row in re.split(r'[;\n\r]+', text) if row.strip()]
        if len(rows) == 1 and rows[0].count('=') > 1:
            # Also accept "x=1, y=2" while leaving malformed equality counts
            # to the equation parser.
            candidates = [part.strip() for part in rows[0].split(',')]
            if len(candidates) > 1 and all('=' in part for part in candidates):
                rows = candidates
    else:
        raise InputIssue()
    if (not rows or len(rows) > MAX_STEPS
            or sum(len(row) for row in rows) > MAX_TEXT * MAX_STEPS
            or any(len(row) > MAX_TEXT for row in rows)):
        raise InputIssue('cannot_verify')
    return rows


def parse_equation(text):
    if not isinstance(text, str) or text.count('=') != 1:
        raise InputIssue()
    left_text, right_text = text.split('=')
    left, right = Parser(left_text).parse(), Parser(right_text).parse()
    expression = left.expr - right.expr
    exclusions = left.exclusions + right.exclusions
    variables = left.variables | right.variables
    return {
        'expr': expression,
        'exclusions': exclusions,
        'variables': variables,
    }


def equation(text):
    """Compatibility entry point retained for callers of the original parser."""
    return parse_equation(text)


def parse_expression(text):
    """Parse an expression plus optional explicit restrictions such as x != 1."""
    import sympy as sp

    pieces = re.split(r';|,|\bwhere\b', normalize(text), flags=re.IGNORECASE)
    base = Parser(pieces[0]).parse()
    exclusions = list(base.exclusions)
    variables = set(base.variables)
    symbols = {'x': sp.Symbol('x', real=True), 'y': sp.Symbol('y', real=True)}
    for condition in pieces[1:]:
        match = re.fullmatch(r'\s*([xy])\s*!\s*=\s*(.*?)\s*', condition)
        if not match:
            raise InputIssue()
        variable, rhs_text = match.groups()
        rhs = Parser(rhs_text).parse()
        exclusions.extend(rhs.exclusions)
        exclusions.append(symbols[variable] - rhs.expr)
        variables.add(variable)
        variables.update(rhs.variables)
    return ParsedExpression(base.expr, exclusions, variables)


def prompt_state(problem):
    if not isinstance(problem, dict):
        raise InputIssue()
    if 'expression' in problem:
        expression = parse_expression(problem['expression'])
        return {
            'kind': 'expression',
            'expr': expression.expr,
            'exclusions': expression.exclusions,
            'variables': expression.variables,
            'scope': str(problem.get('primary_skill_id', problem.get('concept_id', ''))),
        }
    raw = problem.get('equations', problem.get('system', problem.get('equation')))
    if isinstance(raw, str) and '=' not in raw:
        expression = parse_expression(raw)
        return {
            'kind': 'expression',
            'expr': expression.expr,
            'exclusions': expression.exclusions,
            'variables': expression.variables,
            'scope': str(problem.get('primary_skill_id', problem.get('concept_id', ''))),
        }
    rows = split_rows(raw)
    equations = [parse_equation(row) for row in rows]
    variables = frozenset().union(*(eq['variables'] for eq in equations))
    if not variables:
        # Constant equations still belong to the traditional one-variable scope.
        variables = frozenset(('x',))
    if not variables.issubset({'x', 'y'}):
        raise InputIssue('unsupported_scope')
    state = {'kind': 'equations', 'equations': equations, 'variables': variables,
             'scope': str(problem.get('primary_skill_id', problem.get('concept_id', '')))}
    _enforce_scope(state)
    return state


def _enforce_scope(state):
    # Keep the original linear tutor skill constrained to linear rational
    # arithmetic. Broader A/E skill tasks use the bounded quadratic grammar.
    if 'LIN' not in state.get('scope', '').upper():
        return
    for equation_data in state.get('equations', []):
        numerator, denominator = _sp().together(equation_data['expr']).as_numer_denom()
        if denominator.free_symbols:
            raise InputIssue('unsupported_scope')
        if _sp().Poly(numerator, _sp().Symbol('x', real=True),
                      _sp().Symbol('y', real=True)).total_degree() > 1:
            raise InputIssue('unsupported_scope')
        if any(condition.free_symbols for condition in equation_data['exclusions']):
            raise InputIssue('unsupported_scope')


def parse_step(text, task):
    if task['kind'] == 'expression':
        expression = parse_expression(text)
        if expression.variables - task['variables']:
            raise InputIssue('unsupported_scope')
        state = {
            'kind': 'expression', 'expr': expression.expr,
            'exclusions': expression.exclusions, 'variables': task['variables'],
            'scope': task.get('scope', ''),
        }
        _enforce_scope(state)
        return state
    if task['variables'] == frozenset(('x',)) or task['variables'] == frozenset(('y',)):
        alternatives = re.split(r'\s+(?:or|hoặc)\s+|,\s*', normalize(text), flags=re.IGNORECASE)
        if len(alternatives) > 1:
            roots = set()
            for alternative in alternatives:
                equation_data = parse_equation(alternative)
                if equation_data['variables'] - task['variables']:
                    raise InputIssue('unsupported_scope')
                individual = {
                    'kind': 'equations', 'equations': [equation_data],
                    'variables': task['variables'], 'scope': task.get('scope', ''),
                }
                signature = _one_variable_signature(individual)
                if signature[2][0] != 'finite' or len(signature[2][1]) != 1:
                    raise InputIssue('unsupported_scope')
                roots.update(signature[2][1])
            return {'kind': 'solution_set', 'roots': frozenset(roots),
                    'variables': task['variables'], 'scope': task.get('scope', '')}
    rows = split_rows(text)
    equations = [parse_equation(row) for row in rows]
    seen = frozenset().union(*(eq['variables'] for eq in equations))
    if seen - task['variables']:
        raise InputIssue('unsupported_scope')
    state = {'kind': 'equations', 'equations': equations, 'variables': task['variables'],
             'scope': task.get('scope', '')}
    _enforce_scope(state)
    return state


def _sp():
    import sympy as sp
    return sp


def _zero_roots(expr, variable):
    sp = _sp()
    numerator = sp.together(expr).as_numer_denom()[0]
    try:
        polynomial = sp.Poly(numerator, variable)
    except Exception as exc:
        raise InputIssue('unsupported_scope') from exc
    if polynomial.degree() > 2:
        raise InputIssue('unsupported_scope')
    if polynomial.is_zero:
        return ('all', frozenset())
    roots = sp.solveset(polynomial.as_expr(), variable, domain=sp.S.Reals)
    if roots == sp.S.Reals:
        return ('all', frozenset())
    if roots == sp.S.EmptySet:
        return ('finite', frozenset())
    if isinstance(roots, sp.FiniteSet):
        return ('finite', frozenset(sp.simplify(root) for root in roots))
    raise InputIssue('unsupported_scope')


def _domain_signature(exclusions, variables):
    sp = _sp()
    vars_sorted = sorted(variables)
    if len(vars_sorted) <= 1:
        variable = sp.Symbol(vars_sorted[0] if vars_sorted else 'x', real=True)
        forbidden = set()
        for condition in exclusions:
            roots = _zero_roots(condition, variable)
            if roots[0] == 'all':
                return ('empty_domain',)
            forbidden.update(roots[1])
        return ('cofinite_domain', frozenset(forbidden))
    for condition in exclusions:
        numerator = sp.together(condition).as_numer_denom()[0]
        if numerator == 0:
            return ('empty_domain',)
        if numerator.free_symbols:
            raise InputIssue('unsupported_scope')
    return ('full_domain',)


def _intersect_roots(left, right):
    if left[0] == 'all':
        return right
    if right[0] == 'all':
        return left
    return ('finite', left[1] & right[1])


def _filter_roots(roots, exclusions, variable):
    if roots[0] == 'all':
        remaining = set()
        for condition in exclusions:
            excluded = _zero_roots(condition, variable)
            if excluded[0] == 'all':
                return ('finite', frozenset())
            remaining.update(excluded[1])
        return ('cofinite', frozenset(remaining))
    kept = set()
    for root in roots[1]:
        valid = True
        for condition in exclusions:
            if _sp().simplify(condition.subs(variable, root)) == 0:
                valid = False
                break
        if valid:
            kept.add(root)
    return ('finite', frozenset(kept))


def _one_variable_signature(state):
    sp = _sp()
    variable_name = next(iter(state['variables']), 'x')
    variable = sp.Symbol(variable_name, real=True)
    roots = ('all', frozenset())
    exclusions = []
    for equation in state['equations']:
        exclusions.extend(equation['exclusions'])
        roots = _intersect_roots(roots, _zero_roots(equation['expr'], variable))
    domain = _domain_signature(exclusions, {variable_name})
    if domain == ('empty_domain',):
        roots = ('finite', frozenset())
    else:
        roots = _filter_roots(roots, exclusions, variable)
    return ('one_variable_equations', domain, roots)


def _two_variable_signature(state):
    sp = _sp()
    x, y = sp.Symbol('x', real=True), sp.Symbol('y', real=True)
    exclusions = []
    rows = []
    for equation in state['equations']:
        exclusions.extend(equation['exclusions'])
        numerator = sp.together(equation['expr']).as_numer_denom()[0]
        try:
            polynomial = sp.Poly(numerator, x, y)
        except Exception as exc:
            raise InputIssue('unsupported_scope') from exc
        if polynomial.total_degree() > 1:
            raise InputIssue('unsupported_scope')
        rows.append([polynomial.coeff_monomial(x), polynomial.coeff_monomial(y),
                     polynomial.coeff_monomial(1)])
    domain = _domain_signature(exclusions, {'x', 'y'})
    matrix = sp.Matrix(rows)
    reduced, _ = matrix.rref()
    canonical_rows = tuple(
        tuple(sp.simplify(reduced[i, j]) for j in range(3))
        for i in range(reduced.rows)
        if any(reduced[i, j] != 0 for j in range(3))
    )
    return ('two_variable_system', domain, canonical_rows)


def state_signature(state):
    if state['kind'] == 'solution_set':
        return ('solution_set', state['roots'])
    if state['kind'] == 'expression':
        sp = _sp()
        domain = _domain_signature(state['exclusions'], state['variables'])
        canonical = sp.cancel(state['expr'])
        return ('expression', domain, canonical)
    if 'y' in state['variables']:
        return _two_variable_signature(state)
    return _one_variable_signature(state)


def equivalent(left, right):
    if left['kind'] == 'solution_set' and right['kind'] == 'solution_set':
        return left['roots'] == right['roots']
    if left['kind'] == 'solution_set' or right['kind'] == 'solution_set':
        answer, equation_state = (left, right) if left['kind'] == 'solution_set' else (right, left)
        if equation_state['kind'] != 'equations' or 'y' in equation_state['variables']:
            return False
        equation_roots = _one_variable_signature(equation_state)[2]
        return equation_roots == ('finite', answer['roots'])
    if left['kind'] != right['kind']:
        return False
    if left['kind'] == 'expression':
        sp = _sp()
        return (
            _domain_signature(left['exclusions'], left['variables'])
            == _domain_signature(right['exclusions'], right['variables'])
            and sp.cancel(left['expr'] - right['expr']) == 0
        )
    return state_signature(left) == state_signature(right)


def _is_isolated_solution(state, text=None):
    if state['kind'] == 'solution_set':
        return bool(state['roots'])
    if state['kind'] != 'equations':
        return False
    sp = _sp()
    if text is not None:
        try:
            rows = split_rows(text)
            variables = state['variables']
            if len(rows) != len(variables):
                return False
            seen = set()
            for row in rows:
                left_text, right_text = row.split('=')
                left = Parser(left_text).parse()
                right = Parser(right_text).parse()
                isolated_variable = None
                for candidate in variables:
                    symbol = sp.Symbol(candidate, real=True)
                    if left.expr == symbol and not right.expr.free_symbols:
                        isolated_variable = candidate
                        break
                    if right.expr == symbol and not left.expr.free_symbols:
                        isolated_variable = candidate
                        break
                if isolated_variable is None or isolated_variable in seen:
                    return False
                seen.add(isolated_variable)
            return seen == set(variables)
        except (InputIssue, ValueError):
            return False
    if 'y' in state['variables']:
        signature = _two_variable_signature(state)
        rows = signature[2]
        # A solved 2-variable system has the canonical rows x=a and y=b.
        return len(rows) == 2 and rows[0][0] == 1 and rows[0][1] == 0 and rows[1][0] == 0 and rows[1][1] == 1
    if len(state['equations']) != 1:
        return False
    eq = state['equations'][0]
    if _domain_signature(eq['exclusions'], state['variables']) != ('cofinite_domain', frozenset()):
        return False
    variable = sp.Symbol(next(iter(state['variables']), 'x'), real=True)
    expr = sp.together(eq['expr']).as_numer_denom()[0]
    try:
        polynomial = sp.Poly(expr, variable)
    except Exception:
        return False
    return polynomial.degree() == 1


def _is_linear_equation_task(state):
    if state['kind'] != 'equations' or 'y' in state['variables'] or len(state['equations']) != 1:
        return False
    equation_data = state['equations'][0]
    if _domain_signature(equation_data['exclusions'], state['variables']) != ('cofinite_domain', frozenset()):
        return False
    sp = _sp()
    variable = sp.Symbol(next(iter(state['variables']), 'x'), real=True)
    numerator = sp.together(equation_data['expr']).as_numer_denom()[0]
    try:
        return sp.Poly(numerator, variable).degree() == 1
    except Exception:
        return False


def solution(eq):
    """Compatibility helper returning an exact SymPy real solution set."""
    sp = _sp()
    variable = sp.Symbol('x', real=True)
    if isinstance(eq, dict) and 'expr' in eq:
        state = {'kind': 'equations', 'equations': [eq],
                 'variables': eq.get('variables', frozenset(('x',)))}
        if 'y' in state['variables']:
            raise InputIssue('unsupported_scope')
        roots = _one_variable_signature(state)[2]
        if roots[0] == 'finite':
            return sp.FiniteSet(*roots[1])
        if roots[0] == 'cofinite':
            return sp.Complement(sp.S.Reals, sp.FiniteSet(*roots[1]))
        return sp.S.Reals
    if isinstance(eq, (list, tuple)) and len(eq) == 2:
        left, right = eq
        a, b = left[0] - right[0], left[1] - right[1]
        expr = sp.Add(
            sp.Mul(sp.Rational(a), variable, evaluate=True),
            sp.Rational(b),
            evaluate=True,
        )
        return sp.solveset(expr, variable, domain=sp.S.Reals)
    raise InputIssue('unsupported_scope')


def isolated(eq):
    """Compatibility helper for the original exact linear parser callers."""
    if isinstance(eq, dict) and 'expr' in eq:
        return _is_isolated_solution({
            'kind': 'equations', 'equations': [eq],
            'variables': eq.get('variables', frozenset(('x',))),
        })
    if isinstance(eq, (list, tuple)) and len(eq) == 2:
        left, right = eq
        return (left[:2] == (1, 0) and right[0] == 0) or (right[:2] == (1, 0) and left[0] == 0)
    return False


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
        expected = Parser(normalize(problem['task']['expression'])).parse().expr
        for index, line in enumerate(normalized, 1):
            parts = line.split('=')
            values = [Parser(part.strip()).parse() for part in parts]
            if any(value.exclusions or _sp().expand(value.expr - expected) != 0 for value in values):
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
    if not isinstance(steps, (list, tuple)) or any(not isinstance(step, str) for step in steps):
        steps = []
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
    result = {'assessment': assessment('unverified', 'cannot_verify'),
              'normalization': [{'raw': r, 'normalized': n} for r, n in zip(steps, normalized)],
              'progress': 0}

    def finish(status, reason, **fields):
        data = assessment(status, reason)
        data.update(fields)
        result['assessment'] = data
        return result

    if not normalized or not any(s.strip() for s in normalized):
        return finish('needs_clarification', 'ambiguous_input')
    if len(normalized) > MAX_STEPS or any(len(s) > MAX_TEXT for s in normalized):
        return finish('unverified', 'cannot_verify')
    try:
        original = prompt_state(problem)
        task = original
        # A literal repetition of the prompt does not count as a learner step.
        prompt_text = (problem.get('expression', problem.get('equation')) if original['kind'] == 'expression'
                       else problem.get('equations', problem.get('system', problem.get('equation'))))
        prompt_rows = split_rows(prompt_text)
        prompt_trace_text = '; '.join(prompt_rows)
        if len(normalized) and [re.sub(r'\s', '', row) for row in split_rows(normalized[0])] == [
            re.sub(r'\s', '', row) for row in prompt_rows
        ]:
            normalized = normalized[1:]
        if not normalized:
            return finish('needs_clarification', 'ambiguous_input')

        previous = original
        first_error = None
        first_error_text = None
        first_error_before_text = None
        first_error_before_state = None
        first_error_after_state = None
        for index, step in enumerate(normalized, 1):
            try:
                current = parse_step(step, task)
                is_equivalent = equivalent(previous, current)
            except InputIssue:
                if first_error is None:
                    raise
                # Preserve the earliest proven error. An unreadable later line
                # cannot create a second diagnosis or erase the first one.
                continue
            except Exception:
                if first_error is None:
                    raise
                continue
            if not is_equivalent and first_error is None:
                first_error, first_error_text = index, step
                first_error_before_text = prompt_trace_text if index == 1 else normalized[index - 2]
                first_error_before_state = previous
                first_error_after_state = current
            if first_error is None:
                result['progress'] = index
            previous = current

        if first_error is not None:
            # A one-line isolated answer gets the answer-specific reason code,
            # while its mismatch with the prompt still identifies step one.
            single_final = (len(normalized) == 1
                            and _is_isolated_solution(previous, normalized[-1])
                            and _is_linear_equation_task(original))
            evidence = [f'step:{first_error}:not_equivalent']
            fields: dict[str, object] = dict(
                primary_skill_id=problem.get('primary_skill_id'),
                verification_method='symbolic_and_rule',
                evidence=evidence,
                first_error_step=first_error,
            )
            from .misconceptions import detect_misconception
            candidate = detect_misconception(
                problem,
                step_index=first_error,
                before_text=first_error_before_text or '',
                after_text=first_error_text or '',
                previous_steps=normalized[:first_error - 1],
                before_state=first_error_before_state,
                after_state=first_error_after_state,
            )
            fields.update(
                error_family=candidate,
                misconception_candidate=candidate or 'unknown',
                diagnosis_status='suspected' if candidate else 'unverified',
            )
            return finish('verified_incorrect', 'wrong_final_answer' if single_final else
                          'invalid_transformation', **fields)

        if normalized and equivalent(original, previous):
            if (original['kind'] == 'expression'
                    or _is_isolated_solution(previous, normalized[-1])):
                return finish('verified_correct', 'valid_solution',
                              primary_skill_id=problem.get('primary_skill_id'),
                              verification_method='symbolic_and_rule',
                              evidence=['task:verified_solution'])
        return finish('unverified', 'valid_partial', verification_method='symbolic_and_rule',
                      evidence=['task:valid_partial'])
    except InputIssue as exc:
        status = 'needs_clarification' if exc.reason == 'ambiguous_input' else 'unverified'
        return finish(status, exc.reason)
    except Exception:
        # Unsupported symbolic corner cases must fail closed, never take down
        # the tutor request or the sandbox worker.
        return finish('unverified', 'cannot_verify')


def validate_bounded(problem, steps, *, timeout=None):
    """Run the parser in its stdin/stdout worker and always reap timed-out work."""
    try:
        configured = float(os.getenv('VALIDATOR_TIMEOUT_SECONDS', '2.75'))
        requested = configured if timeout is None else float(timeout)
        limit = min(2.75, max(.05, requested))
    except (TypeError, ValueError):
        limit = 2.75
    try:
        completed = subprocess.run([sys.executable, '-m', 'app.math_worker'],
            input=json.dumps({'problem': problem, 'steps': steps}), capture_output=True, text=True,
            encoding='utf-8', timeout=limit, cwd=Path(__file__).resolve().parents[1])
        if completed.returncode:
            raise ValueError('worker_failure')
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {'assessment': assessment('unverified', 'cannot_verify'), 'normalization': [],
                'progress': 0, 'worker_status': 'timeout'}
    except (ValueError, OSError, TypeError):
        return {'assessment': assessment('unverified', 'cannot_verify'), 'normalization': [],
                'progress': 0, 'worker_status': 'worker_failure'}
