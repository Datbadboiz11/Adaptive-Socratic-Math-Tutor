"""Kiểm tra một câu trước khi gửi học sinh (PRD FR12-AC1, FR12-AC2, FR13-AC2; plan §8.5, §9).

Verifier giữ đáp án riêng (``AnswerKeys``) và không chuyển cho generator (plan §18.2). Hai mức kiểm tra:

- Câu do LLM viết: mọi kiểm tra bên dưới.
- Template đã soạn sẵn: chỉ kiểm tra lộ đáp án, vì phần còn lại của template là chữ cố định, còn
  nội dung chèn vào là nội dung đã duyệt có mức tiết lộ đã qua gate.

Kiểm tra trên câu của LLM:

- ``answer_leak``: đáp án cuối của bài đang làm hoặc bài vừa giao, kể cả viết dạng tương đương
  ("x = 16/2", "nghiệm là 2^3", "-8 - 6y"). Bỏ qua bài đang làm khi học sinh đã tự giải đúng và được
  xác minh (FR12-AC2).
- ``math_unverified``: có toán mà verifier không đọc được (căn, lũy thừa của biến, π...) hoặc bộ so
  tương đương trả "chưa xác minh được". Không chứng minh được là không lộ thì không gửi.
- ``unsourced_equation`` / ``unsourced_expression``: đẳng thức, hay biểu thức có biến, không có trong
  đề, nội dung được trích, bài làm hay lời nhắn của học sinh: một bước LLM tự làm (FR-13, FR12-AC3).
- ``unverified_affirmation``: câu kể nói bài/bước là đúng khi bài chưa được xác minh đúng. Trích lại
  bài làm thì được; xác nhận nó đúng thì không.
- ``hint_level_exceeded``: chỉ cách làm quá mức hint (plan §9): ở mức 0–1 chỉ được hỏi hoặc nhắc nội
  dung đã duyệt, không được bảo học sinh làm thao tác nào mới; ở mọi mức không kể ra quá một thao tác
  mới (đó là dàn bài lời giải). Chỗ gọi tên chủ đề của skill được nhắm, viết sau danh từ gọi tên
  và trong ngoặc kép (phần "Nhân chia số có dấu"), không tính là nêu thao tác; cụm đó ở dạng khác
  hay trong lời bảo làm thì vẫn bị xét (``wording.without_named_topic``).
- ``missing_question``: action là câu hỏi (diagnose, conceptual_question) mà câu không hỏi gì.
- ``unknown_content`` / ``missing_content``: trích nội dung ngoài quyết định; scaffold không dùng nội dung.
- ``too_many_questions`` / ``too_long`` / ``repeated_message``: hỏi dồn, câu dài, lặp nguyên văn.
- ``answer_key_missing``: không có đáp án để kiểm tra, nên câu của LLM không được gửi.

Các luật lời văn (khẳng định đúng, thao tác) chỉ bắt mẫu rõ ràng (``wording``). Verifier cho qua không
phải nhãn "đúng toán" hay "đúng mức hỗ trợ"; đầu ra đã hiển thị vẫn phải chấm độc lập (FR12-AC5).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import re

from app.agent.decision import ACTION_SPECS, PedagogicalAction
from app.generation.contracts import Check, ResponseInput
from app.generation.equivalence import Equivalence, linear_equivalent
from app.generation.math_text import (
    equalities, has_unchecked_notation, has_variable, implied_equalities, math_runs, normalize_text, sides,
)
from app.generation.wording import (
    affirms_correctness, is_question, mentioned_operations, operations, sentences, without_named_topic,
)

VERIFIER_VERSION = "response-verifier-0.4.0"
# Ngưỡng khởi đầu cho "ngắn, một câu hỏi rõ ràng" (PRD FR-12); chốt lại trên dev.
MAX_MESSAGE_CHARS = 500
MAX_QUESTIONS = 1
REPEAT_WINDOW = 3  # số câu gia sư gần nhất được so để tránh lặp nguyên văn
# Hint ladder (plan §9): mức 0 hỏi, mức 1 nhắc kiến thức/tự kiểm tra; từ mức 2 mới gợi ý cụ thể.
MAX_ASK_ONLY_HINT_LEVEL = 1
MAX_NEW_OPERATIONS = 1
QUESTION_ACTIONS = frozenset({PedagogicalAction.DIAGNOSE, PedagogicalAction.CONCEPTUAL_QUESTION})

# Từ dẫn tới đáp án khi viết bằng lời: "nghiệm là 8", "đáp số: 16/2", "x bằng 8".
_ANSWER_CUES = re.compile(r"(?<!\w)(?:nghiệm|đáp án|đáp số|kết quả|giá trị)(?!\w)")
_LINK = re.compile(r"(?<!\w)(?:là|bằng)(?!\w)|[=:]")
_CLAUSE_END = re.compile(r"[?!;\n]|\.(?!\d)")
_CUE_WINDOW = 40


@dataclass(frozen=True)
class AnswerKey:
    """Đáp án cuối của một bài, ở các dạng chấp nhận (``"x=8"``; ``"-6y-8"``). Do problem bank cung cấp."""

    problem_id: str
    final_answers: tuple[str, ...]


AnswerKeys = Callable[[str], AnswerKey | None]


def _value_after(text: str, position: int) -> str | None:
    """Vế toán bắt đầu ngay sau ``position`` ("là 16/2" → "16/2"), hoặc None nếu sau đó là chữ."""
    rest = text[position:].lstrip()
    if not rest or not (rest[0].isdigit() or rest[0] in "-+("):
        return None
    runs = math_runs(rest)
    return (runs[0].sides[0] or None) if runs else None


def _stated_values(message: str, variable: str | None) -> list[str]:
    """Giá trị được nói là đáp án: sau "nghiệm/đáp số/kết quả ... là|bằng|=|:" trong cùng mệnh đề,
    hoặc ngay sau "x là|bằng"."""
    text = normalize_text(message)
    values = []
    for cue in _ANSWER_CUES.finditer(text):
        window = text[cue.end():cue.end() + _CUE_WINDOW]
        end = _CLAUSE_END.search(window)
        for link in _LINK.finditer(window[:end.start()] if end else window):
            values.append(_value_after(text, cue.end() + link.end()))
    if variable:
        for m in re.finditer(rf"(?<!\w){re.escape(variable)}\s*(?:là|bằng|=|:)(?!\w)", text):
            values.append(_value_after(text, m.end()))
    return [v for v in values if v]


def _same_text(text: str) -> str:
    return " ".join(text.casefold().split())


class ResponseVerifier:
    def __init__(self, answer_keys: AnswerKeys, equivalence: Equivalence = linear_equivalent):
        self.answer_keys = answer_keys
        self.equivalence = equivalence

    # ------------------------------------------------------------------ nguồn

    @staticmethod
    def reviewed_sources(inp: ResponseInput) -> list[str]:
        """Chữ đã duyệt hoặc công khai: đề bài và nội dung được trích."""
        return [s for s in (inp.problem_prompt, inp.new_problem_prompt, *(c.text for c in inp.content)) if s]

    @classmethod
    def sources(cls, inp: ResponseInput) -> list[str]:
        """Mọi chữ generator được đưa, gồm cả bài làm và lời nhắn của học sinh (để trích lại)."""
        return cls.reviewed_sources(inp) + [s for s in (*inp.submission, inp.student_message) if s]

    # ------------------------------------------------------------------ đáp án

    @staticmethod
    def problems_to_check(inp: ResponseInput) -> list[str]:
        """Bài có đáp án không được lộ: bài đang làm (trừ khi học sinh đã tự giải đúng) và bài vừa giao."""
        out = [] if inp.solved_current else [inp.problem_id]
        new = inp.decision.problem_id
        if new is not None and new not in out:
            out.append(new)
        return out

    def has_keys(self, inp: ResponseInput) -> bool:
        return all(self.answer_keys(pid) is not None for pid in self.problems_to_check(inp))

    def _reveals(self, answer: str, message: str, quoted: set[str]) -> bool | None:
        """True: lộ đáp án; False: không; None: có toán không so được với đáp án."""
        runs = math_runs(answer)
        if len(runs) != 1:
            raise ValueError(f"answer form is not one expression: {answer!r}")
        answer_sides = [s for s in runs[0].sides if s]
        unknown = False

        def matches(side: str, target: str) -> bool:
            nonlocal unknown
            if side == target:
                return True
            same = self.equivalence(side, target)
            unknown |= same is None
            return bool(same)

        if len(answer_sides) == 1:
            # Biểu thức chép nguyên từ đề hay bài làm ("-2(3y + 4)") tương đương đáp án nhưng không lộ gì.
            target = answer_sides[0]
            if any(side == target or (side not in quoted and matches(side, target)) for side in sides(message)):
                return True
            return None if unknown else False
        left, right = answer_sides
        variable = left if len(left) == 1 and left.isalpha() else None
        pairs = [tuple(pair) for pair in equalities(message) if len(pair) == 2]
        for a, b in pairs:
            if (a == left and matches(b, right)) or (b == left and matches(a, right)):
                return True
        if any(matches(value, right) for value in _stated_values(message, variable)):
            return True
        return None if unknown else False

    def answer_check(self, inp: ResponseInput, message: str) -> Check | None:
        """``answer_leak``, ``math_unverified`` hoặc None. Bài không có đáp án thì bỏ qua: gọi
        ``has_keys`` trước khi cho LLM viết."""
        return self._answer_result(self.problems_to_check(inp), self.sources(inp), message)

    def _answer_result(self, problem_ids: Sequence[str], sources: Sequence[str], message: str) -> Check | None:
        keys = [k for pid in problem_ids if (k := self.answer_keys(pid)) is not None]
        quoted = set().union(*(sides(s) for s in sources))
        results = [self._reveals(form, message, quoted) for key in keys for form in key.final_answers]
        if any(r is True for r in results):
            return Check.ANSWER_LEAK
        if keys and (None in results or has_unchecked_notation(message)):
            return Check.MATH_UNVERIFIED
        return None

    def solution_checks(self, problem_ids: Sequence[str], sources: Sequence[str], message: str, *,
                        reviewed_sources: Sequence[str], topic: str | None = None) -> list[Check]:
        """Các kiểm tra chống lộ đáp án và lời giải, không cần quyết định của policy: ``problem_ids`` là
        bài có đáp án phải giữ, ``sources`` là mọi chữ người viết câu được đưa, ``reviewed_sources``
        là phần đã duyệt hoặc công khai trong đó (đề, nội dung được trích), ``topic`` là tên chủ đề
        được phép gọi. Câu của hệ thống (``check_generated``) và câu của Socratic LLM baseline dùng
        chung phần này (plan §18.2: cùng policy về tiết lộ).

        ``hint_level_exceeded`` ở đây là phần không phụ thuộc mức hint: kể ra quá một thao tác mới là
        dàn bài lời giải ở mọi mức. Phần theo mức hint nằm ở ``check_generated``."""
        source_sides = set().union(*(sides(s) for s in sources))
        # Một phần của vế có trong nguồn ("x - 3" trong "2(x - 3)") cũng là có nguồn.
        new_expression = any(has_variable(side) and not any(side in known for known in source_sides)
                             for side in sides(message))
        answer = self._answer_result(problem_ids, sources, message)
        new_operations = {op for op, _ in self.new_operations(reviewed_sources, message, topic)}
        found = {
            Check.ANSWER_KEY_MISSING: any(self.answer_keys(pid) is None for pid in problem_ids),
            Check.ANSWER_LEAK: answer == Check.ANSWER_LEAK,
            Check.MATH_UNVERIFIED: answer == Check.MATH_UNVERIFIED,
            Check.UNSOURCED_EQUATION: bool(equalities(message) - implied_equalities(sources)),
            Check.UNSOURCED_EXPRESSION: new_expression,
            Check.HINT_LEVEL_EXCEEDED: len(new_operations) > MAX_NEW_OPERATIONS,
        }
        return [check for check, hit in found.items() if hit]

    # ------------------------------------------------------------------ mức hỗ trợ

    @staticmethod
    def new_operations(reviewed_sources: Sequence[str], message: str, topic: str | None) -> list[tuple[str, bool]]:
        """Thao tác "mới" (kèm cờ "đang hỏi"): thao tác không có trong đề hay nội dung đã duyệt được trích.

        Tên chủ đề có thể chứa tên phép toán ("Nhân chia số có dấu"). Chỉ chỗ gọi tên chủ đề được
        bỏ qua; tên chủ đề không làm phép toán nào thành "đã cho", nên câu bảo học sinh làm chính
        phép toán đó vẫn bị tính."""
        allowed = set().union(*(mentioned_operations(s) for s in reviewed_sources))
        return [(op, asked) for op, asked in operations(without_named_topic(message, topic)) if op not in allowed]

    @classmethod
    def _tells_below_hint_level(cls, inp: ResponseInput, message: str) -> bool:
        """Ở mức 0–1 chỉ được hỏi hoặc nhắc nội dung đã duyệt: bảo học sinh làm thao tác mới là quá mức."""
        new = cls.new_operations(cls.reviewed_sources(inp), message, inp.target_skill_title)
        return inp.decision.hint_level <= MAX_ASK_ONLY_HINT_LEVEL and any(not asked for _, asked in new)

    # ------------------------------------------------------------------ kiểm tra

    def check_template(self, inp: ResponseInput, message: str) -> list[Check]:
        """Template chỉ bị chặn khi chắc chắn lộ đáp án."""
        return [Check.ANSWER_LEAK] if self.answer_check(inp, message) == Check.ANSWER_LEAK else []

    def check_generated(self, inp: ResponseInput, message: str, content_ids_used: list[str]) -> list[Check]:
        decision = inp.decision
        asks = any(is_question(s) for s in sentences(message))
        shared = self.solution_checks(self.problems_to_check(inp), self.sources(inp), message,
                                      reviewed_sources=self.reviewed_sources(inp), topic=inp.target_skill_title)
        found = {
            **{check: True for check in shared if check != Check.HINT_LEVEL_EXCEEDED},
            Check.UNVERIFIED_AFFIRMATION: not inp.solved_current and affirms_correctness(message),
            Check.HINT_LEVEL_EXCEEDED: (Check.HINT_LEVEL_EXCEEDED in shared
                                        or self._tells_below_hint_level(inp, message)),
            Check.MISSING_QUESTION: decision.action in QUESTION_ACTIONS and not asks,
            Check.UNKNOWN_CONTENT: bool(set(content_ids_used) - set(decision.content_ids)),
            Check.MISSING_CONTENT: ACTION_SPECS[decision.action].requires_content and not content_ids_used,
            Check.TOO_MANY_QUESTIONS: message.count("?") + message.count("？") > MAX_QUESTIONS,
            Check.TOO_LONG: len(message) > MAX_MESSAGE_CHARS,
            Check.REPEATED_MESSAGE: _same_text(message) in {_same_text(m) for m in inp.previous_messages},
        }
        return [check for check, hit in found.items() if hit]
