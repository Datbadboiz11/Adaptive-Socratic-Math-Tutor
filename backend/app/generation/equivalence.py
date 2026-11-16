"""So tương đương hai vế cho phạm vi toán đang hỗ trợ: biểu thức bậc nhất, hệ số hữu tỉ.

Verifier dùng để nhận đáp án viết dạng khác ("16/2", "4·2", "2^3" cho 8; "-8 - 6y" cho "-6y - 8").
Ngoài phạm vi (tích hai biểu thức có biến, chia cho biểu thức có biến, lũy thừa không phải số mũ
nguyên nhỏ, chia cho 0, cú pháp lạ) thì trả ``None``: *chưa xác minh được*, không phải "khác nhau".
Bộ so của Member 1 (SymPy) có thể thay qua kiểu ``Equivalence``. Không dùng ``eval``.

Đầu vào là một vế đã chuẩn hóa bởi ``math_text`` (chữ thường, không khoảng trắng, đã bỏ dấu nhân
trước biến/ngoặc): ``2(x-3)`` là 2·(x - 3), ``3a`` là 3·a.
"""
from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
import re

Equivalence = Callable[[str, str], bool | None]
LinearForm = dict[str, Fraction]  # biến → hệ số; "" là hằng số

MAX_DEPTH = 12
MAX_EXPONENT = 10
_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[a-z]|[-+*/^()]")


class _Unsupported(ValueError):
    pass


def _clean(form: dict) -> LinearForm:
    return {k: v for k, v in form.items() if v != 0}


def _add(a: LinearForm, b: LinearForm, sign: int = 1) -> LinearForm:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, Fraction(0)) + sign * v
    return _clean(out)


def _scale(a: LinearForm, k: Fraction) -> LinearForm:
    return _clean({key: v * k for key, v in a.items()})


def _constant(a: LinearForm) -> Fraction | None:
    return a.get("", Fraction(0)) if set(a) <= {""} else None


def _multiply(a: LinearForm, b: LinearForm) -> LinearForm:
    ka, kb = _constant(a), _constant(b)
    if ka is not None:
        return _scale(b, ka)
    if kb is not None:
        return _scale(a, kb)
    raise _Unsupported("product of two non-constant expressions")


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens, self.i = tokens, 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise _Unsupported("unexpected end")
        self.i += 1
        return token

    def expression(self, depth: int) -> LinearForm:
        if depth > MAX_DEPTH:
            raise _Unsupported("too deep")
        value = self.term(depth)
        while self.peek() in ("+", "-"):
            sign = 1 if self.take() == "+" else -1
            value = _add(value, self.term(depth), sign)
        return value

    # Thứ tự ưu tiên như quy ước thông thường: dấu âm một ngôi lỏng hơn lũy thừa, nên -2^2 = -(2^2) = -4
    # còn (-2)^2 = 4; lũy thừa kết hợp từ phải sang: 2^3^2 = 2^(3^2).
    #   term  := unary (("*" | "/") unary | unary)*      (vế sau không có dấu là nhân ngầm: 2(x-3), 3a)
    #   unary := ("+" | "-") unary | power
    #   power := atom ("^" unary)?

    def term(self, depth: int) -> LinearForm:
        value = self.unary(depth)
        while True:
            token = self.peek()
            if token in ("*", "/"):
                self.take()
                right = self.unary(depth)
                if token == "*":
                    value = _multiply(value, right)
                else:
                    k = _constant(right)
                    if not k:  # chia cho biểu thức có biến hoặc cho 0
                        raise _Unsupported("division")
                    value = _scale(value, 1 / k)
            elif token is not None and (token == "(" or token.isalnum()):
                value = _multiply(value, self.power(depth))  # nhân ngầm: 2(x-3), 3a
            else:
                return value

    def unary(self, depth: int) -> LinearForm:
        if depth > MAX_DEPTH:
            raise _Unsupported("too deep")
        if self.peek() in ("+", "-"):
            sign = 1 if self.take() == "+" else -1
            return _scale(self.unary(depth + 1), Fraction(sign))
        return self.power(depth)

    def power(self, depth: int) -> LinearForm:
        base = self.atom(depth)
        if self.peek() != "^":
            return base
        self.take()
        exponent, k = _constant(self.unary(depth + 1)), _constant(base)
        if k is None or exponent is None or exponent.denominator != 1 or not 0 <= exponent <= MAX_EXPONENT:
            raise _Unsupported("power")
        return _clean({"": k ** int(exponent)})

    def atom(self, depth: int) -> LinearForm:
        token = self.take()
        if token == "(":
            value = self.expression(depth + 1)
            if self.take() != ")":
                raise _Unsupported("unbalanced")
            return value
        if token[0].isdigit():
            return _clean({"": Fraction(token.replace(",", "."))})
        if token.isalpha():
            return {token: Fraction(1)}
        raise _Unsupported(f"unexpected {token!r}")


def linear_form(side: str) -> LinearForm | None:
    """Dạng chuẩn của một vế bậc nhất; None nếu ngoài phạm vi."""
    tokens = _TOKEN.findall(side)
    if not tokens or "".join(tokens) != side:
        return None
    parser = _Parser(tokens)
    try:
        value = parser.expression(0)
    except (_Unsupported, ZeroDivisionError):
        return None
    return value if parser.peek() is None else None


def linear_equivalent(a: str, b: str) -> bool | None:
    """True/False khi cả hai vế nằm trong phạm vi; None khi chưa xác minh được."""
    fa, fb = linear_form(a), linear_form(b)
    if fa is None or fb is None:
        return None
    return fa == fb
