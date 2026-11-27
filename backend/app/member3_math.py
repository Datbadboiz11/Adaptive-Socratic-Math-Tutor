"""Dạng kiểm toán bổ sung cho các concept của Member 3.

Mỗi dạng gồm hai hàm, theo đúng quy ước ``TASK_CHECKS`` của ``authoring_extended_math``:
``expected(expression)`` tính đáp án đúng từ đề, ``answer(expression, response)`` đọc câu trả lời
thành cùng kiểu giá trị để so bằng ``==``. Câu trả lời không đọc được thì ném ``ValueError``.

Chỉ thêm dạng mới, không đổi dạng có sẵn. Dùng chung bộ đọc đa thức chính xác ``authoring_math``
(một biến x, bậc tối đa 2, số hữu tỉ chính xác).

| Dạng | Concept | Đề (``expression``) | Câu trả lời |
|---|---|---|---|
| ``linear_inequality`` | E10 | ``3*x-5<2*x+1`` | ``x<6`` |
| ``log_value`` | F09 | ``log; 2; 32`` · ``sum; 6; 4; 9`` · ``difference; 3; 54; 2`` | ``5`` |
| ``exp_log_equation`` | F10 | ``exp; 2; x+1; 32`` · ``log; 3; 2*x-1; 2`` | ``x=4`` |
| ``vieta`` | E07 | ``sum_product; x*x-7*x+10`` · ``other_root; 2*x*x-9*x+4; 4`` · ``from_sum_product; 9; 20`` | ``S=7; P=10`` · ``x=1/2`` · ``x^2-9x+20=0`` |
| ``quadratic_monotonic`` | F06 | ``x*x-4*x+1`` | ``nghịch biến trên (-∞; 2), đồng biến trên (2; +∞)`` |
| ``slope_intercept`` | F03 | ``linear; 7-2*x`` · ``point; 3; 2; 5`` · ``points; 1,4; 3,10`` | ``a=-2; b=7`` |
| ``special_factoring`` | A08 | ``x*x-9`` | ``(x-3)(x+3)`` |
| ``product_equation`` | E04 | ``(x-2)*(3*x+5)`` · ``x*(x-4)=3*(x-4)`` | ``{2; -5/3}`` |
"""
import ast
from fractions import Fraction
from math import isqrt
import re

from app.authoring_math import linear_solution, polynomial, scalar

MAX_TEXT = 160
FLIP = {'<': '>', '>': '<', '<=': '>=', '>=': '<='}
_UNICODE = str.maketrans({'−': '-', '–': '-', '·': '*', '×': '*', '≤': '<=', '≥': '>=', '∞': 'inf', '²': '^2'})


def _clean(text):
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError('Expected bounded text')
    return text.translate(_UNICODE).strip()


def _fields(text, separator, count=None):
    parts = [part.strip() for part in _clean(text).split(separator)]
    if not all(parts) or (count is not None and len(parts) != count):
        raise ValueError(f'Expected {count or "non-empty"} fields separated by {separator}')
    return parts


def _poly(text):
    """Đa thức học sinh viết tự nhiên: ``x^2``, ``3x``, ``2(x-1)``, ``(x-3)^2``."""
    text = re.sub(r'\s+', '', _clean(text))
    text = re.sub(r'(\([^()]*\))\^2', r'\1*\1', text)
    text = re.sub(r'x\^2', 'x*x', text)
    text = re.sub(r'(?<=[0-9x)])(?=[x(])', '*', text)
    return text


def _sqrt(value):
    """Căn bậc hai hữu tỉ chính xác, hoặc ``None`` nếu không hữu tỉ."""
    if value < 0:
        return None
    n, d = isqrt(value.numerator), isqrt(value.denominator)
    return Fraction(n, d) if n * n == value.numerator and d * d == value.denominator else None


def _linear(text):
    c, a, q = polynomial(text)
    if q or not a:
        raise ValueError('Expected a first-degree expression in x')
    return a, c


def _quadratic(text):
    c, b, a = polynomial(text)
    if not a:
        raise ValueError('Expected a quadratic')
    return a, b, c


def _rational_roots(coefficients):
    c, b, a = coefficients
    if a:
        root = _sqrt(b * b - 4 * a * c)
        if root is None:
            raise ValueError('Expected rational roots')
        return frozenset({(-b - root) / (2 * a), (-b + root) / (2 * a)})
    if b:
        return frozenset({-c / b})
    raise ValueError('Expected an equation in x')


def _labelled(text, names):
    values = {}
    for part in _fields(text, ';', len(names)):
        match = re.fullmatch(r'([A-Za-z])\s*=\s*(.+)', part)
        if not match or match[1].casefold() not in names or match[1].casefold() in values:
            raise ValueError(f'Expected {"; ".join(n + "=..." for n in names)}')
        values[match[1].casefold()] = scalar(match[2].strip())
    return tuple(values[name] for name in names)


# --------------------------------------------------------------------------- E10 bất phương trình bậc nhất

def _inequality(text):
    match = re.fullmatch(r'([^<>=]+)(<=|>=|<|>)([^<>=]+)', re.sub(r'\s+', '', _clean(text)))
    if not match:
        raise ValueError('Expected one inequality with <, >, <= or >=')
    return match.groups()


def inequality_solution(expression):
    left, op, right = _inequality(expression)
    c, a, q = (l - r for l, r in zip(polynomial(_poly(left)), polynomial(_poly(right))))
    if q or not a:
        raise ValueError('Expected a first-degree inequality with a nonzero x coefficient')
    return (op if a > 0 else FLIP[op]), -c / a


def inequality_answer(expression, response):
    left, op, right = _inequality(response)
    if left == 'x':
        return op, scalar(right)
    if right == 'x':
        return FLIP[op], scalar(left)
    raise ValueError('Write the solution as x < value')


# --------------------------------------------------------------------------- F09 logarit

def _log(base, argument):
    """log_base(argument) khi là số hữu tỉ p/q (q ≤ 3, |p| ≤ 36)."""
    if base <= 0 or base == 1 or argument <= 0:
        raise ValueError('Expected a positive base different from 1 and a positive argument')
    if max(base.numerator, base.denominator, argument.numerator, argument.denominator) > 10**6:
        raise ValueError('Logarithm outside the authoring scope')
    for q in (1, 2, 3):
        for p in range(-36, 37):
            if base ** p == argument ** q:
                return Fraction(p, q)
    raise ValueError('Expected a logarithm with an exact rational value')


def log_value(expression):
    mode, *parts = _fields(expression, ';')
    values = [scalar(part) for part in parts]
    if mode == 'log' and len(values) == 2:
        return _log(*values)
    if mode in ('sum', 'difference') and len(values) == 3:
        base, first, second = values
        if first <= 0 or second <= 0:
            raise ValueError('Every logarithm argument must be positive')
        return _log(base, first * second if mode == 'sum' else first / second)
    raise ValueError('Unknown logarithm task')


def log_answer(expression, response):
    return scalar(_clean(response))


# --------------------------------------------------------------------------- F10 phương trình mũ / logarit

def exp_log_solution(expression):
    mode, base, inner, rhs = _fields(expression, ';', 4)
    a, c = _linear(inner)
    b, k = scalar(base), scalar(rhs)
    if mode == 'exp':
        value = _log(b, k)  # biểu thức trong mũ phải bằng log_b(k)
    elif mode == 'log':
        if b <= 0 or b == 1:
            raise ValueError('Expected a positive base different from 1')
        if k.denominator != 1 or abs(k) > 12:
            raise ValueError('Expected an integer right-hand side between -12 and 12')
        value = b ** int(k)  # biểu thức trong log bằng b^k > 0 nên nghiệm luôn thỏa điều kiện
    else:
        raise ValueError('Unknown exponential/logarithmic equation')
    return (value - c) / a


def exp_log_answer(expression, response):
    response = re.sub(r'\s+', '', _clean(response))
    return linear_solution(response) if '=' in response else scalar(response)


# --------------------------------------------------------------------------- E07 hệ thức Viète

def _real_roots(a, b, c):
    if b * b - 4 * a * c < 0:
        raise ValueError('Viète needs real roots')


def vieta(expression):
    mode, *parts = _fields(expression, ';')
    if mode == 'sum_product' and len(parts) == 1:
        a, b, c = _quadratic(parts[0])
        _real_roots(a, b, c)
        return 'sum_product', -b / a, c / a
    if mode == 'other_root' and len(parts) == 2:
        a, b, c = _quadratic(parts[0])
        known = scalar(parts[1])
        if a * known * known + b * known + c != 0:
            raise ValueError('The given value is not a root')
        return 'other_root', -b / a - known
    if mode == 'from_sum_product' and len(parts) == 2:
        s, p = (scalar(part) for part in parts)
        _real_roots(Fraction(1), -s, p)
        return 'from_sum_product', (p, -s, Fraction(1))
    raise ValueError('Unknown Viète task')


def vieta_answer(expression, response):
    mode = _fields(expression, ';')[0]
    if mode == 'sum_product':
        return ('sum_product', *_labelled(response, ('s', 'p')))
    if mode == 'other_root':
        return 'other_root', exp_log_answer(expression, response)
    if mode == 'from_sum_product':
        text = _poly(response)
        if text.count('=') != 1 or not all(text.split('=')):
            raise ValueError('Write a full equation with exactly one = and both sides')
        left, right = text.split('=')
        c, b, a = (l - r for l, r in zip(polynomial(left), polynomial(right)))
        if not a:
            raise ValueError('Expected a quadratic equation')
        return 'from_sum_product', (c / a, b / a, Fraction(1))
    raise ValueError('Unknown Viète task')


# --------------------------------------------------------------------------- F06 khoảng đồng biến / nghịch biến

_DIRECTION = {'đồng biến': 'increasing', 'dong bien': 'increasing',
              'nghịch biến': 'decreasing', 'nghich bien': 'decreasing'}
_PIECE = re.compile(r'(đồng biến|nghịch biến|dong bien|nghich bien)\s*(?:trên|tren)?\s*([(\[][^()\[\]]*[)\]])')


def quadratic_monotonic(expression):
    a, b, _ = _quadratic(expression)
    h = -b / (2 * a)
    left, right = ('decreasing', 'increasing') if a > 0 else ('increasing', 'decreasing')
    return frozenset({(left, 'left', h), (right, 'right', h)})


def _interval(text):
    opening, closing = text[0], text[-1]
    low, high = (part.strip() for part in re.split(r'[;,]', text[1:-1]))
    if low in ('-inf',) and opening == '(' and closing in ')]':
        return 'left', scalar(high)
    if high in ('+inf', 'inf') and closing == ')' and opening in '([':
        return 'right', scalar(low)
    raise ValueError('Expected a half-line (-∞; h) or (h; +∞)')


def monotonic_answer(expression, response):
    text = _clean(response).casefold()
    pieces = _PIECE.findall(text)
    if len(pieces) != 2 or len(_PIECE.sub('', text).strip(' ,;.và')) > 0:
        raise ValueError('Name one increasing and one decreasing half-line')
    result = frozenset((_DIRECTION[name], *_interval(re.sub(r'\s+', '', interval))) for name, interval in pieces)
    if len({direction for direction, *_ in result}) != 2:
        raise ValueError('Name one increasing and one decreasing half-line')
    return result


# --------------------------------------------------------------------------- F03 hệ số góc và tung độ gốc

def slope_intercept(expression):
    mode, *parts = _fields(expression, ';')
    if mode == 'linear' and len(parts) == 1:
        a, c = _linear(parts[0])
        return a, c
    if mode == 'point' and len(parts) == 3:
        a, x0, y0 = (scalar(part) for part in parts)
        if not a:
            raise ValueError('Expected a nonzero slope')
        return a, y0 - a * x0
    if mode == 'points' and len(parts) == 2:
        (x1, y1), (x2, y2) = ([scalar(v) for v in _fields(point, ',', 2)] for point in parts)
        if x1 == x2 or y1 == y2:
            raise ValueError('Expected two points of a first-degree function')
        a = (y2 - y1) / (x2 - x1)
        return a, y1 - a * x1
    raise ValueError('Unknown slope task')


def slope_answer(expression, response):
    return _labelled(response, ('a', 'b'))


# --------------------------------------------------------------------------- A08 phân tích bằng hằng đẳng thức / nhóm

def special_factoring(expression):
    coefficients = polynomial(expression)
    if not coefficients[2]:
        raise ValueError('Expected a quadratic')
    _rational_roots(coefficients)
    return coefficients


def _factors(node):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return [*_factors(node.left), *_factors(node.right)]
    return [node]


def factoring_answer(expression, response):
    text = _poly(response)
    coefficients = polynomial(text)
    linear = 0
    for factor in _factors(ast.parse(text, mode='eval').body):
        c, b, a = polynomial(ast.get_source_segment(text, factor))
        if a:
            raise ValueError('Factor completely into first-degree factors')
        linear += bool(b)
    if linear != 2:
        raise ValueError('Expected a product of two first-degree factors')
    return coefficients


# --------------------------------------------------------------------------- E04 phương trình tích

def product_equation(expression):
    text = _clean(expression)
    left, _, right = text.partition('=')
    return _rational_roots(tuple(l - r for l, r in zip(polynomial(left), polynomial(right or '0'))))


def root_set_answer(expression, response):
    text = re.sub(r'\s+', '', _clean(response))
    if not text.startswith('{') or not text.endswith('}') or text == '{}':
        raise ValueError('Write the solutions as a set, e.g. {2; -5/3}')
    return frozenset(scalar(part) for part in re.split(r'[;,]', text[1:-1]))


MEMBER3_CHECKS = {
    'linear_inequality': (inequality_solution, inequality_answer),
    'log_value': (log_value, log_answer),
    'exp_log_equation': (exp_log_solution, exp_log_answer),
    'vieta': (vieta, vieta_answer),
    'quadratic_monotonic': (quadratic_monotonic, monotonic_answer),
    'slope_intercept': (slope_intercept, slope_answer),
    'special_factoring': (special_factoring, factoring_answer),
    'product_equation': (product_equation, root_set_answer),
}
MEMBER3_TASK_KINDS = frozenset(MEMBER3_CHECKS)
