"""Rubric Socratic (plan §19.2, PRD §9.4) và hợp đồng dữ liệu của quy trình chấm ẩn cấu hình.

Sáu chiều, mỗi chiều 0–2. Lỗi toán nghiêm trọng hoặc tiết lộ lời giải làm lượt đó thất bại dù tổng
điểm cao. Hướng dẫn chấm có ví dụ: docs/implementation/evaluation/socratic-rubric.v1.md. Quy trình và
công cụ: docs/implementation/evaluation/rating-workflow.v1.md.

Luồng dữ liệu:

    SystemOutput (câu của từng hệ thống trên từng tình huống)
        → build_rating_packet: RatingItem / PairItem cho người chấm (không có tên hệ thống) + PacketKey
        → người chấm điền CSV → Rating / PairJudgment
        → score_ratings: độ đồng thuận, điểm cuối, tổng hợp theo hệ thống
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.agent.decision import (
    AssessmentStatus, Contract, DecisionIntent, HintLevel, Identifier, PedagogicalAction,
)
from app.generation.contracts import ResponseSource

# Đổi chiều, mức hay luật cờ nghiêm trọng thì tăng; điểm của hai phiên bản không gộp chung.
RUBRIC_VERSION = "socratic-rubric-0.1.0"


class Dimension(StrEnum):
    MATH_CORRECT = "math_correct"
    ERROR_FOCUS = "error_focus"
    LEARNER_FIT = "learner_fit"
    ELICITS = "elicits"
    NO_REVEAL = "no_reveal"
    CLARITY = "clarity"


DIMENSION_LABELS = {
    Dimension.MATH_CORRECT: "Đúng toán",
    Dimension.ERROR_FOCUS: "Bám lỗi",
    Dimension.LEARNER_FIT: "Phù hợp người học",
    Dimension.ELICITS: "Gợi mở",
    Dimension.NO_REVEAL: "Không tiết lộ",
    Dimension.CLARITY: "Rõ ràng",
}

# Mức 2 lấy nguyên điều kiện đạt của plan §19.2; mức 1 và 0 là phần guideline bổ sung.
LEVELS: dict[Dimension, dict[int, str]] = {
    Dimension.MATH_CORRECT: {
        2: "Không có phát biểu hay biến đổi sai, giữ điều kiện áp dụng.",
        1: "Có chỗ thiếu chính xác nhỏ (diễn đạt, thiếu điều kiện) nhưng không dẫn học sinh tới kết quả sai.",
        0: "Có phát biểu hoặc biến đổi sai.",
    },
    Dimension.ERROR_FOCUS: {
        2: "Hướng đến đúng vấn đề có bằng chứng ở lượt này (bước sai, họ lỗi, bài chưa đọc được...).",
        1: "Liên quan đến bài nhưng chung chung, hoặc chỉ chạm một phần vấn đề.",
        0: "Không liên quan đến vấn đề có bằng chứng, hoặc nhắm vào chỗ không có lỗi.",
    },
    Dimension.LEARNER_FIT: {
        2: "Mức hỗ trợ phù hợp bằng chứng làm bài độc lập, số lần đã được hỗ trợ và lịch sử.",
        1: "Hỗ trợ hơi nhiều hoặc hơi ít so với bằng chứng.",
        0: "Rõ ràng không phù hợp: chỉ cách làm chi tiết khi mới sai lần đầu, hoặc lặp câu hỏi chung khi "
           "học sinh đã bế tắc nhiều lượt.",
    },
    Dimension.ELICITS: {
        2: "Để học sinh thực hiện phần suy luận tiếp theo.",
        1: "Có mời học sinh làm, nhưng câu hỏi chỉ cần đáp có/không hoặc đã làm gần hết phần suy luận.",
        0: "Làm thay phần suy luận tiếp theo, hoặc không mời học sinh làm gì.",
    },
    Dimension.NO_REVEAL: {
        2: "Không đưa đáp án hay lời giải hoàn chỉnh, cũng không đưa bước sửa đúng của bài hiện tại.",
        1: "Lộ một phần: đưa kết quả trung gian hoặc bước sửa đúng của một bước, học sinh vẫn còn ít nhất "
           "một bước biến đổi phải tự làm.",
        0: "Đưa đáp án cuối hoặc lời giải hoàn chỉnh, kể cả viết dạng tương đương hoặc gọi đó là bước sửa "
           "đúng của bước cuối.",
    },
    Dimension.CLARITY: {
        2: "Ngắn, hiểu được, không hỏi dồn nhiều việc.",
        1: "Hiểu được nhưng dài, vòng vo hoặc hỏi hai việc.",
        0: "Khó hiểu, mâu thuẫn hoặc hỏi dồn nhiều việc.",
    },
}

# Lượt không có việc học (tạm dừng, kết thúc phiên) thì hai chiều này không áp dụng ("na").
NOT_APPLICABLE_ALLOWED = frozenset({Dimension.ERROR_FOCUS, Dimension.ELICITS})


class SevereFlag(StrEnum):
    """Vi phạm làm lượt thất bại dù tổng điểm cao (plan §19.2)."""

    SERIOUS_MATH_ERROR = "serious_math_error"
    SOLUTION_REVEALED = "solution_revealed"


SEVERE_LABELS = {
    SevereFlag.SERIOUS_MATH_ERROR: "Lỗi toán nghiêm trọng",
    SevereFlag.SOLUTION_REVEALED: "Tiết lộ đáp án/lời giải",
}
# Cờ nghiêm trọng kéo theo điểm 0 ở chiều tương ứng.
SEVERE_REQUIRES_ZERO = {SevereFlag.SERIOUS_MATH_ERROR: Dimension.MATH_CORRECT,
                        SevereFlag.SOLUTION_REVEALED: Dimension.NO_REVEAL}
# Chiều ngược lại chỉ đúng với "Không tiết lộ": mức 0 của chiều này chính là định nghĩa của cờ, nên điểm 0
# thiếu cờ là phiếu mâu thuẫn và lượt đó sẽ không được tính là thất bại. "Đúng toán" có thể 0 mà không có
# cờ (lỗi nhỏ, dễ nhận ra).
ZERO_REQUIRES_SEVERE = {Dimension.NO_REVEAL: SevereFlag.SOLUTION_REVEALED}

Score = Literal[0, 1, 2]
Stage = Literal["independent", "reconciled"]  # điểm trước hòa giải được giữ nguyên (PRD §9.4)
Choice = Literal["A", "B", "tie"]
SystemName = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.:-]{0,59}$")]
RaterId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,29}$")]
ItemId = Annotated[str, Field(pattern=r"^I[0-9a-f]{8}$")]
PairId = Annotated[str, Field(pattern=r"^P[0-9a-f]{8}$")]
Note = Annotated[str, Field(max_length=500)]
RECONCILED_RATER = "reconciled"


# --------------------------------------------------------------------------- đầu vào

class SystemOutput(Contract):
    """Câu gia sư một hệ thống viết cho một tình huống. Script chạy ablation ghi ra dạng này (JSONL)."""

    scenario_id: Identifier
    system: SystemName  # cấu hình (full, no_kg, rule_policy...) hoặc nguồn câu khi pilot
    message: Annotated[str, Field(min_length=1, max_length=2000)]
    action: PedagogicalAction | None = None
    intent: DecisionIntent | None = None
    hint_level: HintLevel | None = None
    problem_id: Identifier | None = None  # bài mới mà câu giao, nếu có
    response_source: ResponseSource | None = None


# --------------------------------------------------------------------------- người chấm thấy gì

class AssessmentSummary(Contract):
    status: AssessmentStatus
    first_error_step: int | None = None
    error_family: Identifier | None = None
    misconception_candidate: Identifier | None = None
    diagnosis_status: Literal["suspected", "supported", "unknown"] = "unknown"


class SkillEvidence(Contract):
    """Bằng chứng quan sát được của một skill. Không có xác suất mastery: người chấm đánh giá "phù hợp
    người học" từ lịch sử, không lấy giá trị BKT làm chuẩn (PRD §9.4)."""

    skill_id: Identifier
    independent_observations: int = Field(ge=0)
    recent_independent: list[bool] = Field(default_factory=list)
    assisted_correct: int = Field(ge=0)


class HistoryEntry(Contract):
    actor: Literal["student", "tutor"]
    kind: str
    action: PedagogicalAction | None = None
    hint_level: HintLevel | None = None
    assessment_status: AssessmentStatus | None = None


class RatingContext(Contract):
    """Tình huống trước lượt được chấm, giống nhau cho mọi hệ thống (chấm ghép cặp, plan §18.2)."""

    scenario_id: Identifier
    problem: str
    reference_answers: list[str]  # chỉ người chấm thấy, để chấm "đúng toán" và "không tiết lộ"
    trigger: Literal["submit", "request_hint", "message", "pause", "resume"]
    student_work: list[str]
    student_message: str | None = None
    assessment: AssessmentSummary | None = None
    hint_level: HintLevel
    support_turns_on_node: int = Field(ge=0)
    no_progress_turns: int = Field(ge=0)
    reviewing_prerequisite: bool
    skills: list[SkillEvidence]
    history: list[HistoryEntry]


class TutorTurn(Contract):
    """Câu gia sư gửi, kèm bài mới mà câu giao (nếu có). Đề và đáp án bài mới để người chấm đối chiếu
    lỗi toán và tiết lộ trên bài vừa giao; hai hệ thống có thể giao hai bài khác nhau."""

    message: str
    new_problem: str | None = None
    new_problem_answers: list[str] = Field(default_factory=list)


class RatingItem(TutorTurn):
    """Một câu cần chấm. Không chứa tên hệ thống hay quyết định đã tạo ra câu."""

    item_id: ItemId
    context: RatingContext


class PairItem(Contract):
    """Hai câu của hai hệ thống trên cùng tình huống; thứ tự A/B ngẫu nhiên theo từng người chấm."""

    pair_id: PairId
    context: RatingContext
    a: TutorTurn
    b: TutorTurn


# --------------------------------------------------------------------------- người chấm trả về

class Rating(Contract):
    item_id: ItemId
    rater_id: RaterId
    stage: Stage = "independent"
    rubric_version: str = RUBRIC_VERSION
    unratable: bool = False  # không chấm được (câu hỏng, thiếu ngữ cảnh): phải ghi lý do
    scores: dict[Dimension, Score | None] = Field(default_factory=dict)  # None = không áp dụng
    severe: list[SevereFlag] = Field(default_factory=list)
    note: Note | None = None

    @model_validator(mode="after")
    def _consistent(self):
        if (self.stage == "reconciled") != (self.rater_id == RECONCILED_RATER):
            raise ValueError(f"reconciled ratings use rater_id {RECONCILED_RATER!r}, and only they do")
        if self.unratable:
            if self.scores or self.severe or not self.note:
                raise ValueError("an unratable item has no scores or flags, only a note saying why")
            return self
        if set(self.scores) != set(Dimension):
            raise ValueError(f"missing dimensions: {sorted(set(Dimension) - set(self.scores))}")
        not_applicable = {d for d, s in self.scores.items() if s is None}
        if not_applicable - NOT_APPLICABLE_ALLOWED:
            raise ValueError(f"only {sorted(NOT_APPLICABLE_ALLOWED)} may be not applicable")
        if len(set(self.severe)) != len(self.severe):
            raise ValueError("severe flags must be unique")
        for flag in self.severe:
            if self.scores[SEVERE_REQUIRES_ZERO[flag]] != 0:
                raise ValueError(f"{flag} requires {SEVERE_REQUIRES_ZERO[flag]} = 0")
        for dimension, flag in ZERO_REQUIRES_SEVERE.items():
            if self.scores[dimension] == 0 and flag not in self.severe:
                raise ValueError(f"{dimension} = 0 requires the {flag} flag")
        return self

    @property
    def fails(self) -> bool:
        return bool(self.severe)


class PairJudgment(Contract):
    pair_id: PairId
    rater_id: RaterId
    stage: Stage = "independent"
    choice: Choice
    note: Note | None = None

    @model_validator(mode="after")
    def _consistent(self):
        if (self.stage == "reconciled") != (self.rater_id == RECONCILED_RATER):
            raise ValueError(f"reconciled judgments use rater_id {RECONCILED_RATER!r}, and only they do")
        return self


# --------------------------------------------------------------------------- khóa ẩn cấu hình

class ItemKey(Contract):
    item_id: ItemId
    scenario_id: Identifier
    system: SystemName
    action: PedagogicalAction | None = None
    intent: DecisionIntent | None = None
    hint_level: HintLevel | None = None
    response_source: ResponseSource | None = None
    # Từ bộ tình huống: action chấp nhận được / bị cấm, để tính tỷ lệ chọn đúng tập (không do người chấm).
    acceptable_actions: list[PedagogicalAction]
    forbidden_actions: list[PedagogicalAction]


class PairKey(Contract):
    pair_id: PairId
    scenario_id: Identifier
    systems: tuple[SystemName, SystemName]  # (hệ thống tham chiếu, hệ thống so sánh)
    shown_as_a: dict[RaterId, SystemName]  # mỗi người chấm thấy hệ thống nào ở vị trí A


class PacketKey(Contract):
    """Ánh xạ mã → hệ thống. Không đưa cho người chấm."""

    rubric_version: str
    packet_id: Identifier
    seed: int
    source: Annotated[str, Field(min_length=1, max_length=200)]  # file đầu vào hoặc "pilot"
    raters: list[RaterId] = Field(min_length=1)
    items: list[ItemKey]
    pairs: list[PairKey] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self):
        if len(set(self.raters)) != len(self.raters) or RECONCILED_RATER in self.raters:
            raise ValueError(f"rater ids must be unique and not {RECONCILED_RATER!r}")
        ids = [i.item_id for i in self.items] + [p.pair_id for p in self.pairs]
        if len(set(ids)) != len(ids):
            raise ValueError("item and pair ids must be unique")
        if len({(i.scenario_id, i.system) for i in self.items}) != len(self.items):
            raise ValueError("one item per scenario and system")
        for pair in self.pairs:
            if set(pair.shown_as_a) != set(self.raters) or not set(pair.shown_as_a.values()) <= set(pair.systems):
                raise ValueError(f"pair {pair.pair_id}: every rater needs an A side from the pair's systems")
        return self


EXPORTED_MODELS = (SystemOutput, RatingItem, PairItem, Rating, PairJudgment, PacketKey)
