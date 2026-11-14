"""Chốt chặn cho đầu ra của LLM: mỗi đoạn LLM trả về phải là bản chép nguyên văn một biểu thức
trọn vẹn trong bài làm, và không phương trình nào bị bỏ sót.

LLM chỉ được *chọn* đoạn. So khớp theo token (số là một khối, bỏ qua khoảng trắng) nên LLM không
thể đổi số, đổi dấu hay ghép "6 5" thành 65. Ba lỗi bị chặn:

- ``not_verbatim``: đoạn không có trong bài làm, hoặc sai thứ tự (LLM đã sửa hoặc bịa).
- ``partial_span``: đoạn chỉ là một phần của biểu thức (ví dụ "x=6" lấy từ "2x=6", "x=8" lấy từ
  "x=8^2", "√x=8" hay "x=8y").
- ``unextracted_math``: còn ký hiệu toán (dấu "=", phép toán, hoặc ký hiệu ngoài grammar như "^",
  "√", ":") nằm ngoài mọi đoạn (LLM bỏ sót một bước hoặc một phần bài làm).

Ranh giới và phần ngoài đoạn được xét theo *mọi* ký hiệu toán, không chỉ ký hiệu grammar hỗ trợ:
ký hiệu chưa hỗ trợ vẫn là toán học sinh đã viết, bỏ nó đi là đổi bài làm. Ký hiệu được nhận theo
nội dung, không theo loại token: "π", "sin", "f(2)" bị tokenize thành chữ nhưng vẫn là toán.
Từ chỉ phép toán đứng *sát* phương trình ("x = 8 nhân 2", "căn x = 8") cũng là phần còn lại của biểu
thức. Cùng từ đó nằm xa phương trình là lời văn ("em nhân 2 vào ngoặc rồi được x = 8"): luật không
phân biệt được toán viết bằng lời ở giữa câu, phần đó dựa vào lời dặn LLM (``math_in_words``).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.extraction.contracts import Reason
from app.extraction.grammar import (
    MATH_KINDS, MATH_WORDS, SPOKEN_OPERATIONS, Kind, Token, has_math_symbol, tokenize,
)

_LIST_MARKER_MAX_DIGITS = 2
# Danh sách trắng: dấu câu chắc chắn không phải toán khi đứng sát một biểu thức. Mọi dấu khác ("!",
# "°", "&", "#"...) đứng sát biểu thức đều có thể là ký hiệu (giai thừa, độ...); không phân biệt
# được với dấu câu thì coi là toán và hỏi lại, thay vì để biểu thức bị cắt.
_SENTENCE_AFTER = frozenset({".", ",", "?", "…", "”", '"', "»", "’"})
_QUOTES_BEFORE = frozenset({"“", '"', "«", "‘"})
# Dấu câu đứng trước biểu thức, cách một khoảng trắng: kết thúc lời văn ("đúng rồi! x = 8") hoặc ngoặc kép.
_SENTENCE_BEFORE_SPACED = _SENTENCE_AFTER | _QUOTES_BEFORE | {"!"}
_MATH_END = frozenset({Kind.NUM, Kind.VAR, Kind.RP})


class GuardIssue(ValueError):
    def __init__(self, reason: Reason):
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Located:
    """Một đoạn đã định vị trong bài làm: dòng (từ 0) và các token của nó trên dòng đó."""

    line: int
    first: int  # chỉ số token đầu trên dòng
    tokens: tuple[Token, ...]

    @property
    def last(self) -> int:
        return self.first + len(self.tokens) - 1

    def source(self, raw_line: str) -> str:
        return raw_line[self.tokens[0].start:self.tokens[-1].end]


def _find(line: list[Token], wanted: list[tuple], start: int) -> int | None:
    for i in range(start, len(line) - len(wanted) + 1):
        if [t.key for t in line[i:i + len(wanted)]] == wanted:
            return i
    return None


def _is_list_marker(line: list[Token], first: int) -> bool:
    """Đoạn đứng sau số thứ tự đầu dòng: "1) ...", "2. ..." (có khoảng trắng sau dấu)."""
    if first != 2:
        return False
    number, mark = line[0], line[1]
    return (number.kind == Kind.NUM and number.text.isdigit() and len(number.text) <= _LIST_MARKER_MAX_DIGITS
            and (mark.kind == Kind.RP or mark.text == ".") and number.end == mark.start
            and mark.end < line[first].start)


def _is_decimal_mark(mark: Token) -> bool:
    return mark.kind == Kind.PUNCT and mark.text in ".,"


def _attached(left: Token, right: Token) -> bool:
    return left.end == right.start


def _variable_like(token: Token) -> bool:
    """Chữ trông như ẩn: một chữ cái Latin đứng riêng ("y", "a")."""
    return token.kind == Kind.WORD and len(token.text) == 1 and token.text.isascii()


def _is_math_word(line: list[Token], i: int) -> bool:
    """Chữ là ký hiệu toán: tên hàm/hằng ("sin", "pi"), có ký tự toán ("π", "²"), hoặc dính liền
    dấu "(" như một lời gọi hàm ("f(2)", "sin(2)")."""
    token = line[i]
    if token.kind != Kind.WORD:
        return False
    if token.text.lower() in MATH_WORDS or has_math_symbol(token.text):
        return True
    return i + 1 < len(line) and line[i + 1].kind == Kind.LP and _attached(token, line[i + 1])


def _is_spoken_operation(token: Token) -> bool:
    """Từ chỉ phép toán: "nhân", "chia", "mũ", "căn"..."""
    return token.kind == Kind.WORD and token.text.lower() in SPOKEN_OPERATIONS


def _is_label_colon(line: list[Token], i: int) -> bool:
    """Dấu ":" sau nhãn bằng chữ ("Bước 1:", "Đáp số:", "câu a:"): dính liền nhãn, có khoảng trắng
    phía sau. Số hay chữ cái đứng riêng chỉ là nhãn khi đứng sau một chữ lời văn ("8:" hay "y:" thì không)."""
    colon = line[i]
    if colon.text != ":" or i == 0 or not _attached(line[i - 1], colon):
        return False
    if i + 1 < len(line) and _attached(colon, line[i + 1]):
        return False
    label = i - 1
    if line[label].kind == Kind.NUM or _variable_like(line[label]):
        if label == 0:
            return False
        label -= 1
    return line[label].kind == Kind.WORD and not _variable_like(line[label]) and not _is_math_word(line, label)


def _follows_math(line: list[Token], i: int) -> bool:
    """Dấu đứng ngay sau số, ẩn hay ngoặc đóng: "8!", "x'", "5 °" (giai thừa, đạo hàm, độ...)."""
    if i == 0 or line[i - 1].kind not in _MATH_END:
        return False
    token = line[i]
    return token.text == "!" or (_attached(line[i - 1], token) and token.text not in _SENTENCE_AFTER)


def _is_notation(line: list[Token], i: int) -> bool:
    """Token là ký hiệu toán, kể cả ký hiệu grammar chưa hỗ trợ và ký hiệu viết bằng chữ."""
    token = line[i]
    if token.kind in MATH_KINDS or _variable_like(token) or _is_math_word(line, i):
        return True
    if token.kind != Kind.PUNCT:
        return False
    if token.text == ":":
        return not _is_label_colon(line, i)
    return has_math_symbol(token.text) or _follows_math(line, i)


def _punct_cuts_before(line: list[Token], first: int) -> bool:
    """Dấu câu ngay trước đoạn: chỉ dấu ngoặc kép được dính liền; cách một khoảng trắng thì chỉ dấu
    kết câu ("đúng rồi! x = 8"). Dấu khác ("!x", "#x") có thể là ký hiệu."""
    before = line[first - 1]
    if before.text == ":" and _is_label_colon(line, first - 1):
        return False
    if _attached(before, line[first]):
        return before.text not in _QUOTES_BEFORE
    return before.text not in _SENTENCE_BEFORE_SPACED


def _is_prose(line: list[Token], i: int) -> bool:
    """Lời văn: chữ không phải ký hiệu toán."""
    return line[i].kind == Kind.WORD and not _is_notation(line, i)


def _is_prose_comment(line: list[Token], open_index: int) -> bool:
    """Ngoặc chú thích bằng lời: "(chuyển vế)", "(bước 2)". Bên trong chỉ có lời văn, số và dấu câu,
    có ít nhất một chữ, không có ký hiệu toán nào ("(sin 2)", "(2)" thì không phải chú thích)."""
    inside = []
    for j in range(open_index + 1, len(line)):
        if line[j].kind == Kind.RP:
            break
        inside.append(j)
    else:
        return False  # không có ngoặc đóng
    if not any(_is_prose(line, j) for j in inside):
        return False
    return all(_is_prose(line, j) or line[j].kind == Kind.NUM
               or (line[j].kind == Kind.PUNCT and not _is_notation(line, j)) for j in inside)


def _cut_before(line: list[Token], first: int) -> bool:
    if first == 0 or _is_list_marker(line, first):
        return False
    before = line[first - 1]
    if _is_notation(line, first - 1):  # ký hiệu toán ngay trước: biểu thức bắt đầu từ sớm hơn
        return True
    if before.kind == Kind.WORD and (_attached(before, line[first]) or _is_spoken_operation(before)):
        return True  # "căn x = 8": phép toán bằng lời ngay trước
    # "6,5x = 3" mà đoạn là "5x = 3": dấu thập phân dính liền số phía trước.
    if (_is_decimal_mark(before) and _attached(before, line[first]) and first >= 2
            and line[first - 2].kind == Kind.NUM and _attached(line[first - 2], before)):
        return True
    return before.kind == Kind.PUNCT and _punct_cuts_before(line, first)


def _cut_after(line: list[Token], last: int) -> bool:
    if last == len(line) - 1:
        return False
    after = line[last + 1]
    if after.kind == Kind.LP and _is_prose_comment(line, last + 1):
        return False  # chú thích bằng lời trong ngoặc: "2x = 16 (chuyển vế)"
    if _is_notation(line, last + 1):  # ký hiệu toán ngay sau: biểu thức còn tiếp tục
        return True
    if after.kind == Kind.WORD and (_attached(line[last], after) or _is_spoken_operation(after)):
        return True  # "x = 8 nhân 2": biểu thức còn tiếp tục bằng lời
    if after.text == "," and last + 2 < len(line) and _is_spoken_operation(line[last + 2]):
        return True  # "x = 8, nhân 2"
    # "x = 6,5" mà đoạn là "x = 6": phần thập phân bị cắt mất.
    if (_is_decimal_mark(after) and _attached(line[last], after) and last + 2 < len(line)
            and line[last + 2].kind == Kind.NUM and _attached(after, line[last + 2])):
        return True
    # Ngay sau biểu thức chỉ được phép dấu kết câu; "x = 8!" có thể là 8 giai thừa.
    return after.kind == Kind.PUNCT and after.text not in _SENTENCE_AFTER


def occurs_whole(line: list[Token], wanted: list[tuple]) -> bool:
    """Dãy token có xuất hiện trên dòng như một biểu thức trọn vẹn không (dùng để nhận dòng chép đề)."""
    position = _find(line, wanted, 0)
    if position is None:
        return False
    return not _cut_before(line, position) and not _cut_after(line, position + len(wanted) - 1)


def _wanted_sequences(spans: list[str]) -> list[list[tuple]]:
    """Dãy token cần tìm cho từng đoạn. Đoạn chứa mũi tên được tách thành nhiều phương trình."""
    out = []
    for span in spans:
        groups, current = [], []
        for token in tokenize(span):
            if token.kind == Kind.SEP:
                groups.append(current)
                current = []
            else:
                current.append(token.key)
        groups = [g for g in groups + [current] if g]
        if not groups:
            raise GuardIssue(Reason.NOT_VERBATIM)
        out += groups
    return out


def locate_spans(lines: list[list[Token]], spans: list[str]) -> list[Located]:
    """Định vị từng đoạn theo đúng thứ tự xuất hiện. Raise ``GuardIssue`` nếu LLM không trung thành."""
    found: list[Located] = []
    line_no, start = 0, 0
    for wanted in _wanted_sequences(spans):
        position = None
        while line_no < len(lines):
            position = _find(lines[line_no], wanted, start)
            if position is not None:
                break
            line_no, start = line_no + 1, 0
        if position is None:
            raise GuardIssue(Reason.NOT_VERBATIM)
        line = lines[line_no]
        located = Located(line_no, position, tuple(line[position:position + len(wanted)]))
        if _cut_before(line, located.first) or _cut_after(line, located.last):
            raise GuardIssue(Reason.PARTIAL_SPAN)
        found.append(located)
        start = located.last + 1
    require_full_coverage(lines, found)
    return found


def _is_operator_notation(line: list[Token], i: int) -> bool:
    """Ký hiệu cho thấy có toán ở đây: "=", phép toán, ký hiệu ngoài grammar, tên hàm/hằng.
    Số, ẩn x, chữ cái đứng riêng và ngoặc thì không tính, vì cũng xuất hiện trong lời văn
    ("Bước 1", "tìm x", "câu a", "(chuyển vế)")."""
    token = line[i]
    if token.kind in {Kind.EQ, Kind.OP} or _is_math_word(line, i):
        return True
    return token.kind == Kind.PUNCT and _is_notation(line, i)


def require_full_coverage(lines: list[list[Token]], found: list[Located]) -> None:
    """Không ký hiệu toán nào của bài làm được nằm ngoài các đoạn đã tách."""
    covered = {(f.line, i) for f in found for i in range(f.first, f.last + 1)}
    for line_no, line in enumerate(lines):
        for i in range(len(line)):
            if (line_no, i) not in covered and _is_operator_notation(line, i):
                raise GuardIssue(Reason.UNEXTRACTED_MATH)
