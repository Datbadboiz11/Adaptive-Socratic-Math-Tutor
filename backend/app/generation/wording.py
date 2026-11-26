"""Đọc lời văn tiếng Việt của câu phản hồi: tách câu và mệnh đề, lời khẳng định "đúng", thao tác giải.

Đây là luật theo từ ngữ, không hiểu nghĩa câu. Mục tiêu là bắt các mẫu rõ ràng (khen bước sai, kể
ra cách giải ở lượt hỏi chẩn đoán), còn câu lọt qua vẫn phải được chấm độc lập (PRD FR12-AC5).

Luật xét theo **mệnh đề**, không theo dấu "?" cuối câu: trong "Em hãy cộng sáu vào hai vế nhé, em
hiểu chưa?" chỉ mệnh đề sau là câu hỏi, còn mệnh đề trước vẫn là lời chỉ dẫn.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n+")
_CLAUSE_SPLIT = re.compile(r"[;:]|,(?!\d)")  # "6,5" là số thập phân, không phải ranh giới mệnh đề
_WORD = re.compile(r"\w+|[^\w\s]")

# Mệnh đề phụ đứng trước bổ nghĩa cho mệnh đề sau: "khi nhân một số với ngoặc, em nhân với phần nào?"
_SUBORDINATE_STARTS = (("khi",), ("nếu",), ("lúc",), ("mỗi", "khi"), ("trước", "khi"), ("sau", "khi"),
                       ("giả", "sử"))
_QUESTION_WORDS = frozenset({"nào", "gì", "sao", "mấy", "đâu", "bao"})  # "bao" của "bao nhiêu"
# Đứng trước thao tác thì đó là lời bảo làm, kể cả trong câu có dấu hỏi ("em thử cộng 6 xem được gì?").
_IMPERATIVES = frozenset({"hãy", "cần", "phải", "nên", "thử"})
_IMPERATIVE_WINDOW = 3
# Danh từ đứng trước tên một chủ đề: phần "Tính phân phối".
_NAMING_NOUNS = "phần|chủ đề|bài|mục"

# "đúng" theo sau bởi các từ này là câu hỏi hoặc trạng từ ("đúng không", "đúng chưa", "đúng là" = quả thật).
_NOT_AN_AFFIRMATION_AFTER = frozenset({"không", "chưa", "hay", "là", "hông"})
_NEGATIONS = frozenset({"chưa", "không", "chẳng", "chả"})

# Thao tác giải. Từ đơn chỉ tính khi có đối tượng ngay sau ("nhân 2", "cộng sáu vào", "chia cho"), để
# "phép nhân", "chia nhỏ", "trừ khi" không bị tính.
_SINGLE_OPERATIONS = frozenset({"nhân", "chia", "cộng", "trừ"})
_COMPOUND_OPERATIONS = {("chuyển", "vế"): "chuyển vế", ("khai", "triển"): "khai triển", ("rút", "gọn"): "rút gọn",
                        ("thu", "gọn"): "rút gọn", ("phá", "ngoặc"): "phá ngoặc", ("bỏ", "ngoặc"): "phá ngoặc",
                        ("đổi", "dấu"): "đổi dấu"}
_NUMBER_WORDS = frozenset({"một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười", "mươi", "trăm"})
_OBJECT_WORDS = frozenset({"với", "cho", "vào", "thêm", "đi", "cả", "từng", "số"}) | _NUMBER_WORDS


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def is_question(sentence: str) -> bool:
    return sentence.rstrip().endswith(("?", "？"))


def _words(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


@dataclass(frozen=True)
class Clause:
    words: list[str]
    asks: bool  # mệnh đề hỏi: kết thúc bằng "?" hoặc có từ để hỏi (nào, gì, sao, bao nhiêu...)


def clauses(text: str) -> list[Clause]:
    out = []
    for sentence in sentences(text):
        parts = [p.strip() for p in _CLAUSE_SPLIT.split(sentence) if p.strip()]
        pending: list[str] = []
        for i, part in enumerate(parts):
            own = _words(part)
            words = pending + own
            last = i == len(parts) - 1
            if not last and any(tuple(own[:len(start)]) == start for start in _SUBORDINATE_STARTS):
                pending = words  # gộp vào mệnh đề sau
                continue
            pending = []
            asks = (last and is_question(sentence)) or bool(_QUESTION_WORDS & set(words))
            out.append(Clause(words, asks))
    return out


def affirms_correctness(text: str) -> bool:
    """Có mệnh đề nói bài làm/bước là đúng: "đúng rồi", "là phép khai triển đúng", "chính xác". Kể cả
    trong câu hỏi ("vì sao bước 2 đúng?" vẫn ngầm khẳng định). Bỏ qua phủ định ("chưa đúng") và dạng
    hỏi ngay sau ("đúng không", "đúng chưa", "đúng hay sai")."""
    for clause in clauses(text):
        words = clause.words
        for i, word in enumerate(words):
            end = i + 1 if word == "đúng" else i + 2 if words[i:i + 2] == ["chính", "xác"] else None
            if end is None:
                continue
            after = words[end] if end < len(words) else ""
            if after not in _NOT_AN_AFFIRMATION_AFTER and not _NEGATIONS & set(words[max(0, i - 2):i]):
                return True
    return False


def _has_object(word: str) -> bool:
    return word in _OBJECT_WORDS or word[:1].isdigit() or word in ("(", "-") or (len(word) == 1 and "a" <= word <= "z")


def operations(text: str) -> list[tuple[str, bool]]:
    """Các thao tác giải được nêu ra, kèm cờ "đang hỏi": thao tác nằm trong mệnh đề hỏi và không có
    từ mệnh lệnh đứng trước. [("nhân", False), ("cộng", True)]."""
    out = []
    for clause in clauses(text):
        words = clause.words
        for i, word in enumerate(words):
            if i and words[i - 1] == "phép":
                continue
            name = _COMPOUND_OPERATIONS.get(tuple(words[i:i + 2]))
            if name is None and word in _SINGLE_OPERATIONS and i + 1 < len(words) and _has_object(words[i + 1]):
                name = word
            if name is not None:
                told = bool(_IMPERATIVES & set(words[max(0, i - _IMPERATIVE_WINDOW):i]))
                out.append((name, clause.asks and not told))
    return out


def without_named_topic(text: str, topic: str | None) -> str:
    """``text`` sau khi bỏ những chỗ **gọi tên** chủ đề ``topic``, để tên chủ đề chứa tên phép toán
    ("Nhân chia số có dấu") không bị đọc thành thao tác.

    Một cụm trùng tên chủ đề chỉ là tên khi đủ ba điều: đứng sau một danh từ gọi tên (phần, chủ đề,
    bài, mục), nằm trong ngoặc kép, và không có từ mệnh lệnh đứng ngay trước. Mọi trường hợp khác
    được giữ lại để xét như chữ thường: "em hãy thu gọn hạng tử đồng dạng ở vế trái" là lời bảo
    làm, không phải tên."""
    words = (topic or "").split()
    if not words:
        return text
    name = re.compile(rf'(?<!\w)({_NAMING_NOUNS})\s+["“]\s*' + r"\s+".join(map(re.escape, words)) + r'\s*["”]',
                      re.IGNORECASE)

    def drop(match: re.Match) -> str:
        before = _words(text[:match.start()])[-_IMPERATIVE_WINDOW:]
        return match.group() if _IMPERATIVES & set(before) else match.group(1)

    return name.sub(drop, text)


def mentioned_operations(text: str) -> set[str]:
    """Thao tác có nhắc tới ở bất kỳ dạng nào (kể cả "phép nhân"): dùng cho nội dung đã duyệt và đề bài."""
    words = _words(text)
    found = {w for w in words if w in _SINGLE_OPERATIONS}
    return found | {name for pair, name in _COMPOUND_OPERATIONS.items()
                    if any(tuple(words[i:i + 2]) == pair for i in range(len(words)))}
