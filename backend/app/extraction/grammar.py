"""Cú pháp nhập bài g2-v1 ở mức ký hiệu: chuẩn hóa ký tự, tách token, kiểm tra một phương trình.

Đặc tả: docs/implementation/mvp/phase1/INPUT_GRAMMAR.md §2. Module này chỉ kiểm tra *định dạng*.
Không làm toán: phương trình có tuyến tính không, có chia cho 0 không, đúng hay sai là việc của
validator (Member 1). Không dùng ``eval``.

    equation   := expression "=" expression
    expression := term (("+" | "-") term)*
    term       := factor (("*" | "/") factor)*
    factor     := ("+" | "-")? atom
    atom       := NUMBER | "x" | "(" expression ")" | NUMBER "x" | NUMBER "(" expression ")"
    NUMBER     := 1..5 chữ số, tùy chọn dấu chấm + 1..4 chữ số
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata

from app.extraction.contracts import Reason

GRAMMAR_VERSION = "g2-v1"
MAX_DEPTH = 12

# Chuẩn hóa ký tự tất định, giữ nguyên độ dài chuỗi để vị trí token trỏ đúng vào bài làm gốc.
# "X" → "x" là bổ sung so với đặc tả g2-v1 (cần Member 1 xác nhận).
_CHAR_MAP = str.maketrans({"−": "-", "–": "-", "—": "-", "×": "*", "·": "*", "⋅": "*", "÷": "/", "X": "x"})
# Mũi tên nối các bước trên một dòng: coi như dấu ngắt. Chuỗi dài đứng trước để "<=>" không bị
# đọc thành "=>".
_ARROWS = ("<=>", "⟺", "⇔", "↔", "=>", "⟹", "⇒", "->", "→")
SEPARATOR = ";"


def normalize_chars(text: str) -> str:
    out = text.translate(_CHAR_MAP)
    for arrow in _ARROWS:
        out = out.replace(arrow, SEPARATOR * len(arrow))
    return out


class Kind(StrEnum):
    NUM = "num"
    VAR = "var"
    OP = "op"
    EQ = "eq"
    LP = "lp"
    RP = "rp"
    SEP = "sep"      # ngắt giữa hai bước: ";" hoặc mũi tên
    WORD = "word"    # chữ (không phải ẩn x)
    PUNCT = "punct"  # ký tự khác


MATH_KINDS = frozenset({Kind.NUM, Kind.VAR, Kind.OP, Kind.EQ, Kind.LP, Kind.RP})
_SYMBOLS = {"+": Kind.OP, "-": Kind.OP, "*": Kind.OP, "/": Kind.OP, "=": Kind.EQ, "(": Kind.LP, ")": Kind.RP,
            SEPARATOR: Kind.SEP}
_TOKEN = re.compile(r"(?P<num>\d+(?:\.\d+)?)|(?P<word>[^\W\d_]+)|(?P<other>\S)")
_NUMBER = re.compile(r"\d{1,5}(?:\.\d{1,4})?")

# Ký hiệu toán ngoài grammar g2-v1. Không thuộc grammar nhưng vẫn là toán: đứng sát một đoạn thì
# đoạn đó đã bị cắt khỏi biểu thức. ":" xử lý riêng vì còn dùng sau nhãn ("Bước 1:").
UNSUPPORTED_SYMBOLS = frozenset("^√∛∜%|<>≤≥≠≈±∓[]{}∞∑∏∫∂∆∇'")
# Tên hàm và hằng toán viết bằng chữ Latin; tokenize thành WORD nên phải nhận theo nội dung.
MATH_WORDS = frozenset({
    "sin", "cos", "tan", "tg", "cot", "cotg", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
    "log", "ln", "lg", "exp", "sqrt", "abs", "mod", "max", "min", "lim", "pi", "inf", "sgn",
})


# Từ tiếng Việt chỉ phép toán. Đứng sát một phương trình thì phương trình đó còn tiếp tục bằng lời
# ("x = 8 nhân 2", "căn x = 8"). Có dấu và không dấu; bỏ dạng không dấu dễ trùng lời văn ("do", "can").
SPOKEN_OPERATIONS = frozenset({
    "nhân", "chia", "cộng", "trừ", "mũ", "căn", "lần", "phần", "bình", "lập", "lũy", "luỹ", "giai", "độ",
    "nhan", "cong", "tru", "mu", "binh", "luy",
})


def has_math_symbol(text: str) -> bool:
    """Chuỗi có ký tự toán không: ký hiệu ngoài grammar, chữ Hy Lạp (π, α...), chỉ số trên/dưới (²)."""
    return any(ch in UNSUPPORTED_SYMBOLS or "GREEK" in unicodedata.name(ch, "")
               or unicodedata.category(ch) == "No" for ch in text)


@dataclass(frozen=True)
class Token:
    kind: Kind
    text: str
    start: int
    end: int

    @property
    def key(self) -> tuple[Kind, str]:
        return self.kind, self.text


def tokenize(text: str) -> list[Token]:
    """Token của một dòng. Số là một khối: "6 5" là hai số, không bao giờ thành 65."""
    tokens = []
    for m in _TOKEN.finditer(normalize_chars(text)):
        value = m.group()
        if m.lastgroup == "num":
            kind = Kind.NUM
        elif m.lastgroup == "word":
            kind = Kind.VAR if value == "x" else Kind.WORD
        else:
            kind = _SYMBOLS.get(value, Kind.PUNCT)
        tokens.append(Token(kind, value, m.start(), m.end()))
    return tokens


def has_decimal_comma(tokens: list[Token]) -> bool:
    """Số viết liền dấu phẩy rồi số ("6,5")."""
    return any(a.kind == Kind.NUM and b.text == "," and c.kind == Kind.NUM and a.end == b.start and b.end == c.start
               for a, b, c in zip(tokens, tokens[1:], tokens[2:]))


class GrammarIssue(ValueError):
    def __init__(self, reason: Reason):
        super().__init__(reason.value)
        self.reason = reason


def check_equation(tokens: list[Token]) -> str:
    """Trả dạng chuẩn hóa (ghép token, không khoảng trắng) nếu đúng cú pháp một phương trình
    g2-v1; ngược lại raise ``GrammarIssue`` kèm lý do."""
    if not tokens:
        raise GrammarIssue(Reason.SYNTAX)
    if has_decimal_comma(tokens):
        raise GrammarIssue(Reason.DECIMAL_COMMA)
    if any(t.kind not in MATH_KINDS for t in tokens):
        raise GrammarIssue(Reason.UNSUPPORTED_NOTATION)
    equals = sum(t.kind == Kind.EQ for t in tokens)
    if equals != 1:
        raise GrammarIssue(Reason.NO_EQUATION if equals == 0 else Reason.CHAINED_EQUALS)
    if any(t.kind == Kind.NUM and not _NUMBER.fullmatch(t.text) for t in tokens):
        raise GrammarIssue(Reason.SYNTAX)
    for slash, number, after in zip(tokens, tokens[1:], tokens[2:]):
        if slash.text == "/" and number.kind == Kind.NUM and after.kind in {Kind.VAR, Kind.LP}:
            raise GrammarIssue(Reason.AMBIGUOUS_FRACTION)
    parser = _Parser(tokens)
    parser.expression(0)
    parser.expect(Kind.EQ)
    parser.expression(0)
    if parser.peek() is not None:
        raise GrammarIssue(Reason.SYNTAX)
    return "".join(t.text for t in tokens)


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> Token | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def accept(self, kind: Kind, texts: str | None = None) -> bool:
        token = self.peek()
        if token is not None and token.kind == kind and (texts is None or token.text in texts):
            self.i += 1
            return True
        return False

    def expect(self, kind: Kind) -> None:
        if not self.accept(kind):
            raise GrammarIssue(Reason.SYNTAX)

    def expression(self, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise GrammarIssue(Reason.SYNTAX)
        self.term(depth)
        while self.accept(Kind.OP, "+-"):
            self.term(depth)

    def term(self, depth: int) -> None:
        self.factor(depth)
        while self.accept(Kind.OP, "*/"):
            self.factor(depth)

    def factor(self, depth: int) -> None:
        self.accept(Kind.OP, "+-")
        if self.accept(Kind.NUM):
            if not self.accept(Kind.VAR):
                self.group(depth)  # nhân ngầm 2(x-3); không có thì là số đứng riêng
        elif not self.accept(Kind.VAR) and not self.group(depth):
            raise GrammarIssue(Reason.SYNTAX)

    def group(self, depth: int) -> bool:
        if not self.accept(Kind.LP):
            return False
        self.expression(depth + 1)
        self.expect(Kind.RP)
        return True
