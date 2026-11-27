"""Đáp án cuối phải ở dạng gọn, không chỉ đúng giá trị.

Các hàm ``response_value`` tính giá trị câu trả lời, nên một biểu thức chưa tính xong vẫn ra đúng
giá trị: chép lại đề ``5/12+7/18``, mới quy đồng ``15/36+14/36``, mới đi một bước ``x+3=5``. Chế độ
chấm đáp án cuối (``math_validator.validate_member2_answer``) dùng ``is_final_form`` để không tính
các câu trả lời đó là đã làm xong bài.

Mọi số học sinh nộp phải viết gọn: số nguyên, phân số tối giản có mẫu dương khác 1, hoặc số thập phân
hữu hạn. Đề yêu cầu phân số (``phân số tối giản``, ``dạng phân số``) thì không nhận số thập phân:
N06 phải nộp ``-1/4``, không phải ``-0.25``; F10 chỉ yêu cầu tìm x nên nhận cả ``3/2`` và ``1.5``.

Nghiệm chứa căn phải vô tỉ và rút gọn hết, theo một trong hai cách viết:
``(a ± b*sqrt(n))/d`` với a, b, d không còn ước chung, hoặc ``p ± b*sqrt(n)/d`` với p là số gọn và
b, d không còn ước chung. n không chính phương và không còn thừa số chính phương; không viết hệ số 1.

Dạng không có trong bảng không bị giới hạn thêm (đa thức đã có ``check_expanded_quadratic``; nhân tử,
phân thức và bài lập phương trình lời văn có cấu trúc riêng).
"""
from math import gcd, isqrt
import re

INTEGER_OR_FRACTION = r'[+-]?(?:\d+|\d+/\d+)'
DECIMAL = r'[+-]?\d+\.\d+'
_UNICODE = str.maketrans({'−': '-', '–': '-', '≤': '<=', '≥': '>=', '∞': 'inf', 'ℝ': 'R', '∖': '\\', '²': '^2'})


def is_number(text: str, decimals: bool = False) -> bool:
    """Số nguyên, phân số tối giản mẫu dương khác 1, hoặc số thập phân nếu ``decimals``."""
    text = text.strip()
    if decimals and re.fullmatch(DECIMAL, text):
        return True
    if not re.fullmatch(INTEGER_OR_FRACTION, text):
        return False
    if '/' in text:
        numerator, denominator = (int(part) for part in text.lstrip('+-').split('/'))
        return denominator > 1 and gcd(numerator, denominator) == 1
    return True


def _squarefree(n: int) -> bool:
    return n > 1 and all(n % (k * k) for k in range(2, isqrt(n) + 1))


_SURD_TERM = re.compile(r'(?P<sign>[+-]?)(?:(?P<b>\d+)\*)?sqrt\((?P<n>\d+)\)(?:/(?P<d>\d+))?')
FRACTION_REQUIRED = re.compile(r'phân số tối giản|dạng phân số', re.IGNORECASE)


def eval_number(text: str):
    from fractions import Fraction
    return Fraction(text.lstrip('+'))


def _signed_terms(text: str) -> list[str]:
    """Tách ở dấu + và - ngoài ngoặc, giữ dấu cho từng hạng tử (``-1+sqrt(3)`` → ``-1``, ``+sqrt(3)``)."""
    terms, depth, start = [], 0, 0
    for index, char in enumerate(text):
        depth += (char == '(') - (char == ')')
        if char in '+-' and depth == 0 and index > start and text[index - 1] not in '*/(':
            terms.append(text[start:index])
            start = index
    terms.append(text[start:])
    return terms


def _surd(term: str, denominator_allowed: bool):
    """Hệ số b, mẫu d của hạng tử căn đã rút gọn, hoặc ``None``."""
    match = _SURD_TERM.fullmatch(term)
    if not match or (match['d'] and not denominator_allowed):
        return None
    b, d = int(match['b'] or 1), int(match['d'] or 1)
    if match['b'] in ('0', '1') or b == 0 or match['d'] == '1' or not _squarefree(int(match['n'])):
        return None  # hệ số 0 hoặc 1 viết thừa, căn còn rút gọn được
    return b, d


def surd_is_reduced(text: str, decimals: bool = False) -> bool:
    """Một nghiệm chứa đúng một căn vô tỉ, viết ở dạng không còn rút gọn được, hạng tử theo thứ tự bất kỳ:
    ``(a ± b*sqrt(n))/d`` (a, b, d không còn ước chung) hoặc ``p ± b*sqrt(n)/d`` (p gọn, b và d nguyên tố
    cùng nhau). Dấu âm có thể đặt trước ngoặc: ``-(1+sqrt(3))/2``. Phần hữu tỉ ở cách viết thứ hai
    đọc theo cùng quy tắc số như mọi đáp án khác (``decimals``). Hạng tử có hệ số 0 không được tính là
    đã rút gọn."""
    if text.count('sqrt') != 1:
        return False
    grouped = re.fullmatch(r'[+-]?\((.+)\)/(\d+)', text)
    if grouped:
        terms, d = _signed_terms(grouped[1]), int(grouped[2])
        surds = [_surd(term, False) for term in terms if 'sqrt' in term]
        constants = [term for term in terms if 'sqrt' not in term]
        if len(terms) != 2 or len(constants) != 1 or None in surds or d < 2:
            return False
        if not re.fullmatch(r'[+-]?\d+', constants[0]) or int(constants[0]) == 0:
            return False
        return gcd(gcd(abs(int(constants[0])), surds[0][0]), d) == 1
    terms = _signed_terms(text)
    surds = [_surd(term, True) for term in terms if 'sqrt' in term]
    constants = [term for term in terms if 'sqrt' not in term]
    if None in surds or len(surds) != 1 or len(constants) > 1:
        return False
    if constants and (not is_number(constants[0].lstrip('+'), decimals)
                      or float(eval_number(constants[0])) == 0):
        return False
    b, d = surds[0]
    return gcd(b, d) == 1


class Rules:
    def __init__(self, expression: str, prompt: str = ''):
        self.expression = expression
        self.decimals = not FRACTION_REQUIRED.search(prompt or '')

    def number(self, text):
        return is_number(text, self.decimals)

    def numbers(self, parts):
        return all(self.number(part) for part in parts)

    def x_equals(self, text):
        match = re.fullmatch(r'x=(.+)', text)
        return self.number(match[1]) if match else self.number(text)

    def set(self, text):
        return (text.startswith('{') and text.endswith('}') and text != '{}'
                and self.numbers(re.split(r'[;,]', text[1:-1])))

    def labelled(self, text):
        return all(re.fullmatch(r'[A-Za-z]=(.+)', part) and self.number(part.split('=', 1)[1])
                   for part in text.split(';'))

    def interval_ends(self, text):
        ends = re.findall(r'[(\[]([^()\[\]]*)[)\]]', text)
        values = [end for pair in ends for end in re.split(r'[;,]', pair)]
        return bool(values) and all(v in ('-inf', '+inf', 'inf') or self.number(v) for v in values)

    def root(self, text):
        return surd_is_reduced(text, self.decimals) if 'sqrt' in text else self.number(text)

    def quadratic_roots(self, text):
        discriminant, _, roots = text.partition(';')
        if not self.number(discriminant) or not roots.startswith('{') or not roots.endswith('}'):
            return False
        values = [v for v in roots[1:-1].split(',') if v]
        return all(self.root(v) for v in values)

    def domain(self, text):
        return self.set(text[2:]) if text.startswith('R\\') else self.interval_ends(text)

    def elimination(self, text):
        multipliers, _, point = text.partition(';')
        return self.numbers(multipliers.split(',')) and self.interval_ends(point)

    def exponent(self, text):
        if self.expression.startswith('base'):
            return True
        power, _, domain = text.partition(';')
        if domain and domain != 'R':
            return False
        match = re.fullmatch(r'\(?([^()^]+)\)?\^([+-]?\d+)=(.+)', power)
        return bool(match) and self.number(match[1]) and self.number(match[3])

    def vieta(self, text):
        mode = self.expression.partition(';')[0].strip()
        if mode == 'sum_product':
            return self.labelled(text)
        if mode == 'other_root':
            return self.x_equals(text)
        # Lập phương trình: đúng một dấu =, vế phải bằng 0, vế trái đã khai triển và thu gọn.
        if text.count('=') != 1:
            return False
        left, right = text.split('=')
        if right != '0' or not left:
            return False
        from app.authoring_extended_math import check_expanded_quadratic
        from app.member3_math import _poly
        check_expanded_quadratic(_poly(left))
        return True

    def inequality(self, text):
        match = re.fullmatch(r'x(<=|>=|<|>)(.+)', text)
        if match:
            return self.number(match[2])
        match = re.fullmatch(r'(.+?)(<=|>=|<|>)x', text)
        return bool(match) and self.number(match[1])


RULES = {
    'numeric': Rules.number,
    'evaluate': Rules.number,
    'log_value': Rules.number,
    'linear_equation': Rules.x_equals,
    'exp_log_equation': Rules.x_equals,
    'quadratic_axis': lambda r, t: bool(re.fullmatch(r'x=(.+)', t)) and r.number(t[2:]),
    'quadratic_vertex': lambda r, t: bool(re.fullmatch(r'\(([^,]+),([^,]+)\)', t)) and r.numbers(t[1:-1].split(',')),
    'quadratic_roots': Rules.quadratic_roots,
    'function_domain': Rules.domain,
    'linear_elimination': Rules.elimination,
    'exponent_numeric': Rules.exponent,
    'vieta': Rules.vieta,
    'slope_intercept': Rules.labelled,
    'linear_inequality': Rules.inequality,
    'product_equation': Rules.set,
    'quadratic_monotonic': Rules.interval_ends,
}


def is_final_form(kind: str, expression: str, response: str, prompt: str = '') -> bool:
    """Câu trả lời đã ở dạng đáp án cuối chưa (chưa xét đúng sai). ``prompt`` là đề hiển thị cho học
    sinh, dùng để biết đề có bắt buộc viết phân số không."""
    rule = RULES.get(kind)
    if rule is None:
        return True
    text = re.sub(r'\s+', '', response.translate(_UNICODE))
    try:
        return bool(rule(Rules(expression, prompt), text))
    except (ValueError, SyntaxError, ZeroDivisionError):
        return False
