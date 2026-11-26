"""Đọc các đoạn toán trong một câu tiếng Việt để verifier so sánh. Không làm toán, không ``eval``.

Một *đoạn toán* là dãy liền nhau gồm số, biến một chữ cái, phép toán, ngoặc và dấu "=" (hoặc chữ
"bằng" đứng giữa hai biểu thức). Chữ, dấu câu, mũi tên và dấu ngắt kết thúc đoạn, nên
"4x + 1 = 9 → 4x = 8" là hai đoạn. Mỗi đoạn được tách tại "=" thành các *vế* đã chuẩn hóa (chữ
thường, bỏ khoảng trắng, dấu trừ/nhân Unicode về ASCII, bỏ dấu nhân trước biến hoặc ngoặc).

So sánh là so chuỗi sau chuẩn hóa: "16/2" và "8" là hai vế khác nhau. Tương đương toán học cần bộ
kiểm tra của Member 1 (SymPy); xem giới hạn ở docs/implementation/generation/response-generation.v1.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from app.extraction.grammar import MATH_WORDS

_CHAR_MAP = str.maketrans({"−": "-", "–": "-", "—": "-", "×": "*", "·": "*", "⋅": "*", "÷": "/"})
_ARROWS = ("<=>", "⟺", "⇔", "↔", "=>", "⟹", "⇒", "->", "→")
_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+|\S")
_OPERATORS = frozenset("+-*/^")
_EQUALS_WORDS = frozenset({"bằng"})
# Dấu nhân trước biến hoặc ngoặc được bỏ: "3·a" và "3a", "2 × (x − 3)" và "2(x - 3)" là cùng một vế.
_IMPLICIT_TIMES = re.compile(r"(?<=[0-9a-z)])\*(?=[a-z(])")


def normalize_text(text: str) -> str:
    out = text.lower().translate(_CHAR_MAP)
    for arrow in _ARROWS:
        out = out.replace(arrow, " ; ")
    return out


def _kind(token: str) -> str | None:
    if token[0].isdigit():
        return "num"
    if len(token) == 1 and "a" <= token <= "z":
        return "var"
    if token in _OPERATORS:
        return "op"
    if token == "=":
        return "eq"
    if token in "()":
        return token
    return None


@dataclass(frozen=True)
class MathRun:
    """Một đoạn toán. ``sides`` là các vế giữa các dấu "="; đoạn không có "=" có đúng một vế."""

    sides: tuple[str, ...]

    def equalities(self) -> set[frozenset[str]]:
        """Các đẳng thức đoạn này khẳng định: từng cặp vế liền nhau, bỏ vế rỗng ("2x = ?")."""
        return {frozenset(pair) for pair in zip(self.sides, self.sides[1:]) if all(pair)}

    def implied_equalities(self) -> set[frozenset[str]]:
        """Mọi cặp vế của một chuỗi đẳng thức: "a = b = c" cho cả a = c."""
        sides = [s for s in self.sides if s]
        return {frozenset((a, b)) for i, a in enumerate(sides) for b in sides[i + 1:]}


def math_runs(text: str) -> list[MathRun]:
    tokens = _TOKEN.findall(normalize_text(text))
    kinds = [_kind(t) for t in tokens]
    runs, current = [], []

    def close():
        if current:
            runs.append(MathRun(tuple(_IMPLICIT_TIMES.sub("", "".join(current)).split("="))))
            current.clear()

    for i, (token, kind) in enumerate(zip(tokens, kinds)):
        if kind is None and token in _EQUALS_WORDS and current and kinds[i - 1] in {"num", "var", ")"} \
                and i + 1 < len(tokens) and kinds[i + 1] in {"num", "var", "(", "op"}:
            kind, token = "eq", "="  # "2x bằng 16" là một đẳng thức viết bằng lời
        if kind is None:
            close()
        else:
            current.append(token)
    close()
    return runs


def equalities(text: str) -> set[frozenset[str]]:
    return set().union(*(run.equalities() for run in math_runs(text)))


def implied_equalities(texts: list[str]) -> set[frozenset[str]]:
    return set().union(*(run.implied_equalities() for text in texts for run in math_runs(text)))


def sides(text: str) -> set[str]:
    return {side for run in math_runs(text) for side in run.sides if side}


def has_variable(side: str) -> bool:
    return any("a" <= ch <= "z" for ch in side)


# Toán mà verifier không đọc được: căn, bất đẳng thức, trị tuyệt đối, chữ Hy Lạp (π), chỉ số trên (²),
# tên hàm, phép toán đọc bằng lời ("căn 64", "8 mũ 2"). Câu có chúng thì chưa xác minh được.
_UNCHECKED_SYMBOLS = frozenset("√∛∜≤≥≠≈±∓∞∑∏∫∂∆∇<>|%")
# Tên hàm và phép toán bằng lời chỉ tính khi đứng trước số, biến hoặc ngoặc ("căn 64", "sin(2)"), để
# "căn cứ", "bình tĩnh", "tan học" không bị tính.
_ARGUMENT = r"(?=\s*(?:\d|\(|[a-z](?!\w)|bậc))"
_FUNCTIONS = "|".join(sorted(MATH_WORDS | {"căn", "mũ"}, key=len, reverse=True))
_UNCHECKED_WORDS = re.compile(  # "lập phương trình" là lập phương trình, không phải lập phương
    rf"(?<!\w)(?:(?:{_FUNCTIONS}){_ARGUMENT}|bình phương|lập phương(?!\s*trình)|lũy thừa|luỹ thừa)(?!\w)")


def has_unchecked_notation(text: str) -> bool:
    normalized = normalize_text(text)
    return bool(_UNCHECKED_WORDS.search(normalized)) or any(
        ch in _UNCHECKED_SYMBOLS or "GREEK" in unicodedata.name(ch, "") or unicodedata.category(ch) == "No"
        for ch in normalized)
