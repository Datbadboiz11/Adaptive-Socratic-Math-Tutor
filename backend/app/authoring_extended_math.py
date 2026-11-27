"""Exact checks for the bounded original authoring pilot formats."""
import ast
from fractions import Fraction
from math import gcd, isqrt
import re

import sympy as sp

from app.authoring_math import linear_solution, pair, polynomial, scalar


def fields(text, separator, count):
    parts = [part.strip() for part in text.split(separator)]
    if len(text) > 160 or len(parts) != count or not all(parts):
        raise ValueError(f'Expected {count} fields separated by {separator}')
    return parts


def literal_fraction(text):
    if not re.fullmatch(r'[+-]?\d{1,5}/[1-9]\d{0,4}', text):
        raise ValueError('Expected a fraction with positive denominator')
    numerator, denominator = map(int, text.split('/'))
    return Fraction(numerator, denominator), denominator


def compare_fractions(expression):
    left, right = [literal_fraction(p)[0] for p in fields(expression, '?', 2)]
    return left, '<' if left < right else '>' if left > right else '=', right


def comparison_answer(expression, response):
    parts = re.fullmatch(r'([^<=>]+)\s*([<=>])\s*([^<=>]+)', response)
    if not parts:
        raise ValueError('Expected two fractions and their comparison')
    left, left_denominator = literal_fraction(parts[1].strip())
    right, right_denominator = literal_fraction(parts[3].strip())
    if left_denominator != right_denominator:
        raise ValueError('The comparison response must use a common denominator')
    return left, parts[2], right


def conversion_value(text):
    text = text.replace(',', '.')
    if '/' in text:
        return literal_fraction(text)[0]
    if not re.fullmatch(r'[+-]?\d{1,5}(?:\.\d{1,4})?%?', text):
        raise ValueError('Expected a bounded decimal or percent literal')
    return Fraction(text[:-1]) / 100 if text.endswith('%') else Fraction(text)


def conversion_answer(expression, response):
    _, target = fields(expression, ' -> ', 2)
    value = conversion_value(response)
    if target == 'fraction' and response != f'{value.numerator}/{value.denominator}':
        raise ValueError('Expected a reduced fraction')
    if target == 'percent' and not response.endswith('%'):
        raise ValueError('Expected a percent')
    if target == 'decimal' and ('/' in response or response.endswith('%')):
        raise ValueError('Expected a decimal')
    if target not in ('fraction', 'percent', 'decimal'):
        raise ValueError('Unknown target representation')
    return value


def factored_answer(expression, response):
    coefficients = polynomial(response)
    factors = ast.parse(response, mode='eval').body
    if not isinstance(factors, ast.BinOp) or not isinstance(factors.op, ast.Mult):
        raise ValueError('Expected an explicit product')
    if not any(sum(v != 0 for v in polynomial(ast.get_source_segment(response, side))) == 1
               for side in (factors.left, factors.right)):
        raise ValueError('Expected a monomial common factor')
    target = polynomial(expression)
    if not any(target) or any(c.denominator != 1 for c in target):
        raise ValueError('Expected a nonzero polynomial with integer coefficients')
    degree = next(i for i, c in enumerate(target) if c)
    common = gcd(*(c.numerator for c in target))
    if not any(polynomial(ast.get_source_segment(response, side)) == tuple(
        common if i == degree else 0 for i in range(3)
    ) for side in (factors.left, factors.right)):
        raise ValueError('Expected the positive greatest monomial factor')
    return coefficients


def check_expanded_quadratic(response):
    """Check the answer is a sum of distinct monomials in the bounded grammar."""
    polynomial(response)

    def terms(node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            yield from terms(node.left)
            yield from terms(node.right)
        else:
            yield node

    def monomial(node):
        if isinstance(node, (ast.Constant, ast.Name)):
            return True
        if isinstance(node, ast.UnaryOp):
            return monomial(node.operand)
        return (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div))
                and monomial(node.left) and monomial(node.right))

    degrees = set()
    for term in terms(ast.parse(response, mode='eval').body):
        if not monomial(term):
            raise ValueError('Expand all products of sums')
        coefficients = polynomial(ast.unparse(term))
        degree = next((i for i, value in enumerate(coefficients) if value), 0)
        if degree in degrees:
            raise ValueError('Collect like terms')
        degrees.add(degree)


def real_rational_roots(coefficients):
    c, b, a = coefficients
    if not a:
        if not b and not c:
            raise ValueError('Zero polynomial has infinitely many roots')
        return frozenset([-c / b] if b else [])
    discriminant = b*b - 4*a*c
    if discriminant < 0:
        return frozenset()
    top, bottom = isqrt(discriminant.numerator), isqrt(discriminant.denominator)
    if top * top != discriminant.numerator or bottom * bottom != discriminant.denominator:
        raise ValueError('Pilot requires a rational square discriminant or no real roots')
    root = Fraction(top, bottom)
    return frozenset([(-b - root) / (2*a), (-b + root) / (2*a)])


X = sp.Symbol('x')


def rational_parts(text):
    numerator, denominator = [polynomial(part) for part in fields(text, '|', 2)]
    symbols = [sp.Poly.from_list(list(reversed(p)), X, domain=sp.QQ) for p in (numerator, denominator)]
    return (*symbols, real_rational_roots(denominator))


def rational_operation(expression):
    operation, left, right = fields(expression, ';', 3)
    a, b, excluded_left = rational_parts(left)
    c, d, excluded_right = rational_parts(right)
    excluded = excluded_left | excluded_right
    if operation == '+':
        result = (a*d + b*c) / (b*d)
    elif operation == '-':
        result = (a*d - b*c) / (b*d)
    elif operation == '*':
        result = (a*c) / (b*d)
    elif operation == '/':
        excluded |= real_rational_roots(tuple(Fraction(c.nth(i)) for i in range(3)))
        result = (a*d) / (b*c)
    else:
        raise ValueError('Unknown rational operation')
    return sp.cancel(result), excluded


def rational_simplify(expression):
    """Simplify one rational expression while retaining its original domain."""
    numerator, denominator, excluded = rational_parts(expression)
    return sp.cancel(numerator / denominator), excluded


def rational_simplify_answer(expression, response):
    fraction, domain = fields(response, ';', 2)
    a, b, _ = rational_parts(fraction)
    if sp.gcd(a, b).degree() > 0:
        raise ValueError('Expected the fraction in reduced form')
    return sp.cancel(a / b), parse_set(domain)


def square_root(expression):
    value = scalar(expression)
    if value < 0:
        raise ValueError('The arithmetic square root requires a nonnegative radicand')
    return sp.sqrt(sp.Rational(value.numerator, value.denominator))


def square_root_answer(expression, response):
    text = response.strip().replace(' ', '')
    if text.startswith('-sqrt(') and text.endswith(')'):
        value = scalar(text[6:-1])
        if value < 0:
            raise ValueError('A real square root requires a nonnegative radicand')
        return -sp.sqrt(sp.Rational(value.numerator, value.denominator))
    elif text.startswith('sqrt(') and text.endswith(')'):
        text = text[5:-1]
        value = scalar(text)
        if value < 0:
            raise ValueError('A real square root requires a nonnegative radicand')
        return sp.sqrt(sp.Rational(value.numerator, value.denominator))
    return scalar(text)


def rational_equation(expression):
    """Solve `numerator|denominator; numerator|denominator` over the reals."""
    left, right = fields(expression, ';', 2)
    a, b, excluded_left = rational_parts(left)
    c, d, excluded_right = rational_parts(right)
    excluded = excluded_left | excluded_right
    numerator = a*d - c*b
    coefficients = tuple(Fraction(numerator.nth(i)) for i in range(3))
    solutions = real_rational_roots(coefficients) - excluded
    return excluded, solutions


def rational_equation_answer(expression, response):
    restrictions, solutions = fields(response, ';', 2)
    if not restrictions.startswith('x!='):
        raise ValueError('State all excluded denominator values as x!=...')
    excluded_text = restrictions[3:]
    excluded = frozenset() if excluded_text in ('none', '{}') else frozenset(
        scalar(part) for part in excluded_text.split(',')
    )
    if not solutions.startswith('S='):
        raise ValueError('State the solution set as S={...}')
    return excluded, parse_set(solutions[2:])


def linear_function_sign(expression):
    c, b, a = polynomial(expression)
    if a or not b:
        raise ValueError('Expected a linear function with nonzero slope')
    root = -c / b
    return root, ('>' if b > 0 else '<'), root, ('<' if b > 0 else '>'), root


def linear_function_sign_answer(expression, response):
    text = re.sub(r'\s+', '', response)
    match = re.fullmatch(
        r'x=([^;]+);positive:x([<>])([^;]+);negative:x([<>])(.+)', text,
    )
    if not match:
        raise ValueError('Expected root and positive/negative half-lines')
    root, positive_direction, positive_root, negative_direction, negative_root = match.groups()
    return scalar(root), positive_direction, scalar(positive_root), negative_direction, scalar(negative_root)


def quadratic_sign(expression):
    operator, polynomial_text = fields(expression, ';', 2)
    if operator not in ('sign', '>', '>=', '<', '<='):
        raise ValueError('Expected sign, >, >=, < or <=')
    c, b, a = polynomial(polynomial_text)
    if not a:
        raise ValueError('Expected a quadratic trinomial')
    roots = tuple(sorted(real_rational_roots((c, b, a))))
    leading_sign = '+' if a > 0 else '-'
    if not roots:
        signs = (leading_sign,)
    elif len(roots) == 1:
        signs = (leading_sign, '0', leading_sign)
    else:
        opposite = '-' if leading_sign == '+' else '+'
        signs = (leading_sign, '0', opposite, '0', leading_sign)
    solution = None
    if operator != 'sign':
        wants_positive = operator in ('>', '>=')
        inclusive = operator in ('>=', '<=')
        leading_positive = leading_sign == '+'
        if not roots:
            solution = 'all' if leading_positive == wants_positive else 'empty'
        elif len(roots) == 1:
            if leading_positive == wants_positive:
                solution = 'all' if inclusive else 'all_except_root'
            else:
                solution = 'singleton_root' if inclusive else 'empty'
        else:
            outer = leading_positive == wants_positive
            region = 'outside' if outer else 'inside'
            endpoint = 'closed' if inclusive else 'open'
            solution = f'{region}_{endpoint}'
        solution = _interval_solution(roots, solution)
    return roots, signs, solution


def _interval_solution(roots, form):
    if form == 'empty':
        return ()
    if form == 'all':
        return ((None, False, None, False),)
    if form == 'all_except_root':
        root = roots[0]
        return ((None, False, root, False), (root, False, None, False))
    if form == 'singleton_root':
        root = roots[0]
        return ((root, True, root, True),)
    left, right = roots
    region, endpoint = form.split('_')
    closed = endpoint == 'closed'
    if region == 'inside':
        return ((left, closed, right, closed),)
    return ((None, False, left, closed), (right, closed, None, False))


def parse_interval_solution(text):
    text = re.sub(r'\s+', '', text).replace('∞', 'inf').replace('∪', 'U')
    if text in ('R', 'ℝ'):
        return ((None, False, None, False),)
    if text in ('{}', 'empty', '∅'):
        return ()
    if text.startswith('{') and text.endswith('}'):
        values = parse_set(text)
        return tuple(sorted(((value, True, value, True) for value in values), key=lambda item: item[0]))
    parsed = []
    for interval in text.split('U'):
        match = re.fullmatch(r'(\[|\()([^,]+),([^\]\)]+)(\]|\))', interval)
        if not match:
            raise ValueError('Use real interval notation for the inequality solution')
        left_bracket, lower_text, upper_text, right_bracket = match.groups()
        if lower_text in ('-inf', '-∞'):
            lower, lower_closed = None, False
        else:
            lower, lower_closed = scalar(lower_text), left_bracket == '['
        if upper_text in ('inf', '+inf', '∞', '+∞'):
            upper, upper_closed = None, False
        else:
            upper, upper_closed = scalar(upper_text), right_bracket == ']'
        if lower is not None and upper is not None:
            if lower > upper or (lower == upper and not (lower_closed and upper_closed)):
                raise ValueError('Invalid or empty interval')
        parsed.append((lower, lower_closed, upper, upper_closed))
    return tuple(sorted(parsed, key=lambda item: (item[0] is not None, item[0] or Fraction(0))))


def quadratic_sign_answer(expression, response):
    operator, _ = fields(expression, ';', 2)
    expected_fields = 2 if operator == 'sign' else 3
    parts = fields(response, ';', expected_fields)
    if not parts[0].startswith('roots=') or not parts[1].startswith('signs='):
        raise ValueError('Expected roots and signs')
    roots = parse_set(parts[0][6:])
    signs_text = parts[1][6:]
    signs = tuple(sign.strip() for sign in signs_text.split(','))
    if not signs or any(sign not in ('+', '-', '0') for sign in signs):
        raise ValueError('Sign chart uses only +, - and 0')
    solution = None
    if expected_fields == 3:
        if not parts[2].startswith('solution='):
            raise ValueError('State the inequality solution')
        solution = parse_interval_solution(parts[2][9:])
    return tuple(sorted(roots)), signs, solution


def rational_answer(expression, response):
    fraction, domain = fields(response, ';', 2)
    a, b, _ = rational_parts(fraction)
    if sp.gcd(a, b).degree() > 0:
        raise ValueError('Expected the fraction in reduced form')
    return sp.cancel(a / b), parse_set(domain)


def parse_set(text):
    if not text.startswith('{') or not text.endswith('}'):
        raise ValueError('Expected a set in braces')
    return frozenset(scalar(part.strip()) for part in text[1:-1].split(',')) if text != '{}' else frozenset()


def equation_submission(text):
    variable, unit, restriction, equation = fields(text, ';', 4)
    restriction = {'nguyên dương': 'positive_integer', 'nguyên không âm': 'nonnegative_integer'}.get(restriction, restriction)
    if variable != 'x' or restriction not in ('positive_integer', 'nonnegative_integer'):
        raise ValueError('Expected x, a unit and the declared whole-number range')
    linear_solution(equation)
    left, right = (polynomial(part) for part in fields(equation, '=', 2))
    return variable, unit, restriction, tuple(sorted((left, right)))


def word_equation(expression):
    mode = expression.partition(';')[0].strip()
    if mode == 'difference':
        _, gap, total, unit = fields(expression, ';', 4)
        values = (gap, total)
        equation = f'x+(x+{gap})={total}'
    elif mode in ('groups', 'remaining'):
        _, first, second, third, unit = fields(expression, ';', 5)
        values = (first, second, third)
        equation = f'{first}*x+{second}={third}' if mode == 'groups' else f'{first}-{second}*x={third}'
    else:
        return equation_submission(expression)  # Existing v1 authoring records.
    if not all(re.fullmatch(r'[1-9]\d{0,3}', value) for value in values):
        raise ValueError('Expected bounded positive quantities from the word problem')
    solution = linear_solution(equation)
    if solution <= 0 or solution.denominator != 1:
        raise ValueError('The data must give a positive whole-number solution')
    return equation_submission(f'x; {unit}; positive_integer; {equation}')


def exact_root(text):
    if 'sqrt' not in text:
        return sp.Rational(scalar(text))
    match = re.search(r'\bsqrt\(\s*(\d{1,10}(?:/\d{1,10})?)\s*\)', text)
    if not match or 'x' in text or text.count('sqrt') != 1:
        raise ValueError('Use one exact square root per root, e.g. (1+sqrt(5))/2')
    c, b, a = polynomial(text[:match.start()] + 'x' + text[match.end():])
    if a:
        raise ValueError('Use a linear expression in the square root')
    return sp.Rational(c) + sp.Rational(b) * sp.sqrt(sp.Rational(Fraction(match[1])))


def quadratic_roots(expression):
    c, b, a = polynomial(expression)
    if not a:
        raise ValueError('Expected a quadratic')
    discriminant = b*b - 4*a*c
    if discriminant < 0:
        return discriminant, frozenset()
    center = sp.Rational(-b/(2*a))
    offset = sp.sqrt(sp.Rational(discriminant)) / sp.Rational(2*a)
    return discriminant, frozenset((center - offset, center + offset))


def quadratic_roots_answer(expression, response):
    discriminant, roots = fields(response, ';', 2)
    if not roots.startswith('{') or not roots.endswith('}'):
        raise ValueError('Write the roots as a set in braces')
    values = roots[1:-1].strip()
    return scalar(discriminant), frozenset(exact_root(part.strip()) for part in values.split(',')) if values else frozenset()


def system_rows(expression):
    rows = []
    for row in fields(expression, ';', 2):
        parts = re.fullmatch(r'([+-]?\d{1,3})\*x([+-]\d{1,3})\*y=([+-]?\d{1,4})', row)
        if not parts:
            raise ValueError('Expected ax+by=c with explicit integer coefficients')
        rows.append(tuple(map(int, parts.groups())))
    return rows


def solve_system(expression):
    (a, b, c), (d, e, f) = system_rows(expression)
    determinant = a*e - b*d
    if not determinant:
        raise ValueError('Expected a unique system solution')
    return Fraction(c*e - b*f, determinant), Fraction(a*f - c*d, determinant)


def elimination_answer(expression, response):
    multipliers, coordinates = fields(response, ';', 2)
    m, n = [scalar(part) for part in fields(multipliers, ',', 2)]
    (a, b, _), (d, e, _) = system_rows(expression)
    if not m or not n or (m*a + n*d == 0) == (m*b + n*e == 0):
        raise ValueError('Multipliers must cancel exactly one variable')
    return pair(coordinates)


def substitution_answer(expression, response):
    variable, row, coordinates = fields(response, ';', 3)
    if variable not in ('x', 'y') or row not in ('1', '2'):
        raise ValueError('Name the isolated variable and source equation')
    a, b, _ = system_rows(expression)[int(row) - 1]
    if (variable == 'x' and not a) or (variable == 'y' and not b):
        raise ValueError('The selected equation cannot isolate that variable')
    return pair(coordinates)


def function_domain(expression):
    mode, inner = fields(expression, ';', 2)
    c, b, a = polynomial(inner)
    if a or not b:
        raise ValueError('Expected a linear denominator or radicand')
    boundary = -c/b
    if mode == 'den':
        return 'exclude', frozenset([boundary])
    if mode == 'sqrt':
        return ('lower' if b > 0 else 'upper'), boundary
    raise ValueError('Unknown domain kind')


def domain_answer(expression, response):
    response = re.sub(r'\s+', '', response).translate(str.maketrans({'ℝ': 'R', '∖': '\\', '∞': 'inf', '−': '-'}))
    if response.startswith('R\\'):
        return 'exclude', parse_set(response[2:])
    if response.startswith('[') and response.endswith(',+inf)'):
        return 'lower', scalar(response[1:-6])
    if response.startswith('(-inf,') and response.endswith(']'):
        return 'upper', scalar(response[6:-1])
    raise ValueError('Expected an exclusion or a closed half-line')


def quadratic_axis(expression):
    _, b, a = polynomial(expression)
    if not a:
        raise ValueError('Expected a quadratic')
    return -b/(2*a)


def axis_answer(expression, response):
    variable, value = fields(response, '=', 2)
    if variable != 'x':
        raise ValueError('Expected a vertical axis x = value')
    return scalar(value)


def bounded_power(base, exponent):
    if not 0 < base <= 16 or base == 1 or base.denominator > 16:
        raise ValueError('Expected a small positive base different from 1')
    if exponent.denominator != 1 or abs(exponent) > 12:
        raise ValueError('Expected an integer exponent between -12 and 12')
    return base, exponent, base**int(exponent)


def exponent_value(expression):
    operation, base, left, right = fields(expression, ';', 4)
    a, m, n = scalar(base), scalar(left), scalar(right)
    for exponent in (m, n):
        bounded_power(a, exponent)
    rules = {'product': m + n, 'quotient': m - n, 'power': m*n}
    if operation not in rules:
        raise ValueError('Unknown exponent rule')
    return bounded_power(a, rules[operation])


def exponent_answer(expression, response):
    power, value = fields(response, '=', 2)
    base, exponent = fields(power, '^', 2)
    a, n, _ = bounded_power(scalar(base), scalar(exponent))
    return a, n, scalar(value)


def exponential_value(expression):
    mode, _, rest = expression.partition(';')
    if mode == 'base':
        base = scalar(rest.strip())
        return 'R' if base > 0 and base != 1 else 'khong-phai-ham-mu'
    if mode == 'function':
        return exponent_value(rest), 'R'
    return exponent_value(expression)


def exponential_answer(expression, response):
    mode = expression.partition(';')[0]
    if mode == 'base':
        domain = response.strip().casefold()
        if domain in ('r', 'ℝ'):
            return 'R'
        if domain in ('không phải hàm số mũ', 'khong-phai-ham-mu'):
            return 'khong-phai-ham-mu'
        raise ValueError('State R or that the base does not define an exponential function')
    if mode == 'function':
        power, domain = fields(response, ';', 2)
        if domain in ('R', 'ℝ'):
            domain = 'R'
        return exponent_answer(expression, power), domain
    return exponent_answer(expression, response)


TASK_CHECKS = {
    'fraction_compare': (compare_fractions, comparison_answer),
    'number_conversion': (lambda text: conversion_value(fields(text, ' -> ', 2)[0]), conversion_answer),
    'factored_polynomial': (polynomial, factored_answer),
    'rational_operation': (rational_operation, rational_answer),
    'rational_simplify': (rational_simplify, rational_simplify_answer),
    'square_root': (square_root, square_root_answer),
    'rational_equation': (rational_equation, rational_equation_answer),
    'linear_function_sign': (linear_function_sign, linear_function_sign_answer),
    'quadratic_sign': (quadratic_sign, quadratic_sign_answer),
    'word_equation': (word_equation, lambda expression, response: equation_submission(response)),
    'quadratic_roots': (quadratic_roots, quadratic_roots_answer),
    'linear_elimination': (solve_system, elimination_answer),
    'linear_substitution': (solve_system, substitution_answer),
    'function_domain': (function_domain, domain_answer),
    'quadratic_axis': (quadratic_axis, axis_answer),
    'exponent_numeric': (exponential_value, exponential_answer),
}

# Dạng kiểm của Member 3: thêm vào, không thay dạng có sẵn.
from app.member3_math import MEMBER3_CHECKS  # noqa: E402

TASK_CHECKS.update({kind: check for kind, check in MEMBER3_CHECKS.items() if kind not in TASK_CHECKS})
