"""Bounded learner grammar and task-aware completion for the authoring pilot.

Only full expression snapshots are supported, not arbitrary natural-language proofs.
Trusted task values use the authoring arithmetic; learner input has its own parser.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from math import gcd
import re

from app.math_validator import InputIssue, normalize

ZERO = (F(0), F(0), F(0))
NUMBER = r'\d{1,5}(?:\.\d{1,4})?'


@dataclass(frozen=True)
class Value:
    coefficients: tuple
    has_variable: bool = False


class Parser:
    def __init__(self, text):
        text = normalize(text)
        if not text or len(text) > 160:
            raise InputIssue('ambiguous_input' if not text else 'cannot_verify')
        if re.search(r'/\s*[+-]?\s*\d+(?:\.\d+)?\s*[x(]', text):
            raise InputIssue()  # 1/2x is ambiguous; require (1/2)*x.
        if re.search(r'[<>√]|\*\*|\b[y-z]\b', text):
            raise InputIssue('unsupported_scope')
        text = re.sub(r'x\s*\^\s*2(?!\d)', '(x*x)', text)
        if '^' in text:
            raise InputIssue('unsupported_scope')
        self.tokens = []
        at = 0
        while at < len(text):
            if text[at:].isspace():
                break
            match = re.match(r'\s*(\d+(?:\.\d+)?|x|[()+*/-])', text[at:])
            if not match:
                raise InputIssue()
            self.tokens.append(match[1]); at += match.end()
        self.at = self.nodes = 0

    def peek(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else ''

    def take(self):
        if not self.peek():
            raise InputIssue()
        token = self.peek(); self.at += 1
        return token

    def bounded(self, coefficients, variable=False):
        self.nodes += 1
        if self.nodes > 80 or any(max(v.numerator.bit_length(), v.denominator.bit_length()) > 256 for v in coefficients):
            raise InputIssue('cannot_verify')
        return Value(tuple(coefficients), variable)

    def expression(self, depth=0):
        value = self.term(depth)
        while self.peek() in ('+', '-'):
            sign = 1 if self.take() == '+' else -1
            right = self.term(depth)
            value = self.bounded([a + sign*b for a, b in zip(value.coefficients, right.coefficients)],
                                 value.has_variable or right.has_variable)
        return value

    def term(self, depth):
        value = self.factor(depth)
        while self.peek() in ('*', '/', 'x', '('):
            operator = self.take() if self.peek() in ('*', '/') else '*'
            right = self.factor(depth)
            a, b = value.coefficients, right.coefficients
            if operator == '/':
                if right.has_variable:
                    raise InputIssue('unsupported_scope')
                if b[0] == 0:
                    raise InputIssue()
                value = self.bounded([v/b[0] for v in a], value.has_variable)
            else:
                product = [F(0)]*5
                for i, x in enumerate(a):
                    for j, y in enumerate(b):
                        product[i+j] += x*y
                if any(product[3:]):
                    raise InputIssue('unsupported_scope')
                value = self.bounded(product[:3], value.has_variable or right.has_variable)
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
        elif token == 'x':
            value = Value((F(0), F(1), F(0)), True)
        elif re.fullmatch(NUMBER, token):
            value = Value((F(token), F(0), F(0)))
        else:
            raise InputIssue()
        return self.bounded([sign*v for v in value.coefficients], value.has_variable)

    def parse(self):
        value = self.expression()
        if self.peek():
            raise InputIssue()
        return value


def expression(text):
    return Parser(text).parse()


def scalar(text):
    value = expression(text)
    if value.has_variable:
        raise InputIssue('unsupported_scope')
    return value.coefficients[0]


def equation_value(text):
    if text.count('=') != 1:
        raise InputIssue()
    left, right = [expression(s) for s in text.split('=')]
    a = left.coefficients[1] - right.coefficients[1]
    b = left.coefficients[0] - right.coefficients[0]
    if left.coefficients[2] or right.coefficients[2]:
        raise InputIssue('unsupported_scope')
    # Include empty/all-real solution sets: these are verifiably non-equivalent.
    solution = ('unique', -b/a) if a else ('all' if b == 0 else 'empty', None)
    isolated = ((left.coefficients == (0, 1, 0) and not right.has_variable) or
                (right.coefficients == (0, 1, 0) and not left.has_variable))
    return solution, isolated


def compact(text):
    return re.sub(r'\s+', '', normalize(text))


def literal_scalar(text):
    return re.fullmatch(rf'[+-]?{NUMBER}(?:/[1-9]\d{{0,4}})?', compact(text)) is not None


def reduced_fraction(text):
    match = re.fullmatch(r'([+-]?\d{1,5})/([1-9]\d{0,4})', compact(text))
    return bool(match and gcd(abs(int(match[1])), int(match[2])) == 1)


def simplified_polynomial(text):
    """At most one literal-coefficient monomial per degree; no residual arithmetic."""
    text = compact(text).replace('x^2', 'x*x')
    coefficient = rf'{NUMBER}(?:/[1-9]\d{{0,4}})?'
    term = rf'[+-]?(?:{coefficient}\*?x(?:\*x)?|x(?:\*x)?|{coefficient})'
    matches = list(re.finditer(term, text))
    if not matches or ''.join(m[0] for m in matches) != text:
        return False
    if any(not m[0].startswith(('+', '-')) for m in matches[1:]):
        return False
    degrees = [m[0].count('x') for m in matches]
    return len(degrees) == len(set(degrees))


def factored_polynomial(text):
    """Pilot reverse-distribution form: non-unit rational times a linear factor."""
    text = compact(text)
    coefficient = rf'[+-]?{NUMBER}(?:/[1-9]\d{{0,4}})?'
    match = re.fullmatch(rf'({coefficient})\*?\(([^()]+)\)', text)
    if match:
        factor, inner = match.groups()
    else:
        match = re.fullmatch(rf'\(([^()]+)\)\*({coefficient})', text)
        if not match:
            return False
        inner, factor = match.groups()
    p = expression(inner).coefficients
    return abs(scalar(factor)) not in (0, 1) and p[1] != 0 and p[2] == 0


def value_and_completion(problem, text):
    """Return exact semantic value and whether the requested form is complete."""
    task = problem.task
    text = normalize(text)
    if task.kind == 'linear_equation':
        if '=' in text:
            value, complete = equation_value(text)
            return value, complete
        return ('unique', scalar(text)), literal_scalar(text)
    if task.kind == 'quadratic_vertex':
        if not text.startswith('(') or not text.endswith(')') or text.count(',') != 1:
            raise InputIssue()
        a, b = text[1:-1].split(',')
        return (scalar(a), scalar(b)), literal_scalar(a) and literal_scalar(b)
    # Chains such as 3(x+2)=3x+6 must be valid on BOTH sides.
    segments = text.split('=')
    if len(segments) > 4 or any(not s.strip() for s in segments):
        raise InputIssue()
    values = []
    for segment in segments:
        value = expression(segment)
        p = value.coefficients
        if task.kind == 'polynomial':
            values.append(p)
        elif task.kind == 'numeric':
            if value.has_variable:
                raise InputIssue('unsupported_scope')
            values.append(p[0])
        else:
            x = scalar(task.variable_value)
            values.append(p[0] + p[1]*x + p[2]*x*x)
    last = segments[-1]
    if task.kind == 'polynomial':
        complete = factored_polynomial(last) if task.answer_form == 'factored_polynomial' else simplified_polynomial(last)
    else:
        complete = literal_scalar(last)
        if problem.concept_id == 'N04':
            complete = reduced_fraction(last)
    return tuple(values), complete
