"""Exact bounded arithmetic/polynomial checks for authored fixtures, not learner grading."""
import ast
from fractions import Fraction as F
import re


def polynomial(text):
    if not text or len(text) > 160 or not re.fullmatch(r'[0-9x+*/().\s-]+', text):
        raise ValueError('Unsupported authoring expression')
    tree = ast.parse(text, mode='eval')
    if len(list(ast.walk(tree))) > 80:
        raise ValueError('Expression too complex')

    def bounded(p):
        if len(p) > 3 or any(max(v.numerator.bit_length(), v.denominator.bit_length()) > 256 for v in p):
            raise ValueError('Polynomial exceeds authoring scope')
        return p

    def visit(node, depth=0):
        if depth > 12:
            raise ValueError('Expression too deep')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            literal = ast.get_source_segment(text, node)
            if not re.fullmatch(r'\d{1,5}(?:\.\d{1,4})?', literal):
                raise ValueError('Invalid numeric literal')
            return (F(literal), F(0), F(0))
        if isinstance(node, ast.Name) and node.id == 'x':
            return (F(0), F(1), F(0))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth + 1)
            return value if isinstance(node.op, ast.UAdd) else tuple(-v for v in value)
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                sign = 1 if isinstance(node.op, ast.Add) else -1
                return bounded(tuple(x + sign*y for x, y in zip(a, b)))
            if isinstance(node.op, ast.Mult):
                values = [F(0)]*5
                for i, x in enumerate(a):
                    for j, y in enumerate(b):
                        values[i+j] += x*y
                if any(values[3:]):
                    raise ValueError('Degree greater than two')
                return bounded(tuple(values[:3]))
            if isinstance(node.op, ast.Div) and b[1:] == (0, 0) and b[0] != 0:
                return bounded(tuple(x/b[0] for x in a))
        raise ValueError('Unsupported operator or variable denominator')

    return visit(tree.body)


def scalar(text):
    values = polynomial(text)
    if values[1:] != (0, 0):
        raise ValueError('Expected scalar')
    return values[0]


def linear_solution(text):
    if len(text) > 160 or text.count('=') != 1:
        raise ValueError('Expected one bounded linear equation')
    left, right = (polynomial(s.strip()) for s in text.split('='))
    a = left[1] - right[1]
    if left[2] != 0 or right[2] != 0 or a == 0:
        raise ValueError('Expected unique linear solution')
    return (right[0] - left[0])/a


def pair(text):
    text = text.strip()
    if len(text) > 160 or not text.startswith('(') or not text.endswith(')') or text.count(',') != 1:
        raise ValueError('Expected ordered pair')
    return tuple(scalar(s.strip()) for s in text[1:-1].split(','))


def expected(task):
    p = polynomial(task.expression) if task.kind != 'linear_equation' else None
    if task.kind == 'numeric':
        return scalar(task.expression)
    if task.kind == 'evaluate':
        x = scalar(task.variable_value or '')
        return p[0] + p[1]*x + p[2]*x*x
    if task.kind == 'polynomial':
        return p
    if task.kind == 'linear_equation':
        return linear_solution(task.expression)
    if task.kind == 'quadratic_vertex' and p[2] != 0:
        x = -p[1]/(2*p[2])
        return (x, p[0] + p[1]*x + p[2]*x*x)
    raise ValueError('Unsupported task')


def response_value(task, response):
    if task.kind in ('numeric', 'evaluate'):
        return scalar(response)
    if task.kind == 'polynomial':
        return polynomial(response)
    if task.kind == 'linear_equation':
        return linear_solution(response) if '=' in response else scalar(response)
    if task.kind == 'quadratic_vertex':
        return pair(response)
    raise ValueError('Unsupported response')


def audit_case(case):
    target = expected(case.task)
    if response_value(case.task, case.reference_answer) != target:
        raise ValueError(f'Wrong reference answer: {case.case_id}')
    for step in case.reference_steps:
        if response_value(case.task, step) != target:
            raise ValueError(f'Wrong authored reference step: {case.case_id}')


def first_error(problem, steps):
    """First divergence only: later carried-forward errors are not new diagnoses."""
    target = expected(problem.task)
    for index, step in enumerate(steps, 1):
        if response_value(problem.task, step) != target:
            return index
    return None
