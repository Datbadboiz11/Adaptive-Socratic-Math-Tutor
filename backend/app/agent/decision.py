"""Hợp đồng quyết định sư phạm của Agent: bộ action chuẩn, PedagogicalDecision và StudentState.

Bản nháp v1 để nhóm chốt (plan §8.6, §9, §10; PRD FR-10, FR-11, §6.4).
Giải thích thiết kế: docs/implementation/agent/pedagogical-decision.v1.md

Phân tầng kiểm tra:
- Module này chỉ kiểm tra *hình dạng* một quyết định (action có intent, mức hint, trường bắt buộc
  hợp lệ). Mã lỗi bắt đầu bằng ``S``.
- Luật phụ thuộc state (ví dụ backtrack quá 2 tầng, mức hint nhảy cóc, content ID không được
  truy xuất trong lượt) thuộc policy gate, làm ở bước sau với mã lỗi ``G``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, get_args
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ContractVersion = Literal["agent-contract-0.1.0"]
CONTRACT_VERSION: str = get_args(ContractVersion)[0]

MAX_HINT_LEVEL = 4
MAX_BACKTRACK_DEPTH = 2
MAX_TOOL_CALLS = 3
MAX_REGENERATIONS = 1
MAX_SUPPORT_TURNS_PER_NODE = 6
MAX_CONTEXT_EDGES = 24  # số cạnh prerequisite (1–2 tầng) tối đa trong context một lượt

MAX_SUBMISSION_LINES = 12  # grammar nhập bài g2-v1: tối đa 12 bước, 160 ký tự/bước
MAX_SUBMISSION_LINE_LENGTH = 160

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
SubmissionLine = Annotated[str, Field(min_length=1, max_length=MAX_SUBMISSION_LINE_LENGTH)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
HintLevel = Annotated[int, Field(ge=0, le=MAX_HINT_LEVEL)]
ShortText = Annotated[str, Field(min_length=1, max_length=300)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Bộ action chuẩn (PRD FR-10) và mục đích (intent) của từng action
# ---------------------------------------------------------------------------

class PedagogicalAction(StrEnum):
    CLARIFY = "clarify"
    DIAGNOSE = "diagnose"
    MINIMAL_HINT = "minimal_hint"
    CONCEPTUAL_QUESTION = "conceptual_question"
    BACKTRACK = "backtrack"
    SCAFFOLD = "scaffold"
    CHECK_TRANSFER = "check_transfer"
    NEXT_PROBLEM = "next_problem"
    END_SESSION = "end_session"


class DecisionIntent(StrEnum):
    """Mục đích cụ thể của action. Đây không phải bộ strategy thứ hai (PRD FR-10):
    mỗi intent chỉ thuộc đúng một action và cho generator biết cần viết loại câu nào."""

    # clarify
    RESOLVE_INPUT = "resolve_input"
    RESTATE_TASK = "restate_task"
    # diagnose
    ELICIT_REASONING = "elicit_reasoning"
    DISTINGUISH_HYPOTHESIS = "distinguish_hypothesis"
    PROBE_PREREQUISITE = "probe_prerequisite"
    # minimal_hint
    PROMPT_SELF_CHECK = "prompt_self_check"
    LOCATE_ERROR = "locate_error"
    RECALL_RULE = "recall_rule"
    # conceptual_question
    TARGET_MISCONCEPTION = "target_misconception"
    # scaffold
    DECOMPOSE_STEP = "decompose_step"
    ANALOGOUS_EXAMPLE = "analogous_example"
    EXPLAIN_CONCEPT = "explain_concept"
    # backtrack
    REVIEW_PREREQUISITE = "review_prerequisite"
    # check_transfer
    INDEPENDENT_CHECK = "independent_check"
    # next_problem
    CONTINUE_PRACTICE = "continue_practice"
    ADVANCE_DIFFICULTY = "advance_difficulty"
    ADVANCE_CONCEPT = "advance_concept"
    RETURN_TO_PARENT = "return_to_parent"
    SWITCH_PROBLEM = "switch_problem"
    # end_session
    STUDENT_REQUEST = "student_request"
    SESSION_GOAL_MET = "session_goal_met"
    BUDGET_EXHAUSTED = "budget_exhausted"
    STUCK_LIMIT = "stuck_limit"
    CONTENT_EXHAUSTED = "content_exhausted"
    SYSTEM_FALLBACK = "system_fallback"


@dataclass(frozen=True)
class ActionSpec:
    """Ràng buộc hình dạng của một action. ``hint_levels`` là mức hỗ trợ của chính phản hồi
    theo thang 0–4 ở plan §9."""

    intents: frozenset[DecisionIntent]
    hint_levels: frozenset[int]
    requires_target_skill: bool
    requires_evidence: bool
    requires_edges: bool = False
    requires_problem: bool = False
    requires_content: bool = False
    counts_as_assistance: bool = True
    summary: str = ""


A, I = PedagogicalAction, DecisionIntent

ACTION_SPECS: dict[PedagogicalAction, ActionSpec] = {
    A.CLARIFY: ActionSpec(
        intents=frozenset({I.RESOLVE_INPUT, I.RESTATE_TASK}), hint_levels=frozenset({0}),
        requires_target_skill=False, requires_evidence=True, counts_as_assistance=False,
        summary="Input chưa rõ, không chấm được hoặc học sinh hiểu sai đề; chưa cập nhật BKT."),
    A.DIAGNOSE: ActionSpec(
        intents=frozenset({I.ELICIT_REASONING, I.DISTINGUISH_HYPOTHESIS, I.PROBE_PREREQUISITE}),
        hint_levels=frozenset({0}), requires_target_skill=True, requires_evidence=True,
        summary="Hỏi để phân biệt nguyên nhân lỗi hoặc kiểm tra prerequisite; chưa đưa cách sửa."),
    A.MINIMAL_HINT: ActionSpec(
        intents=frozenset({I.PROMPT_SELF_CHECK, I.LOCATE_ERROR, I.RECALL_RULE}),
        hint_levels=frozenset({1, 2}), requires_target_skill=True, requires_evidence=True,
        summary="Gợi ý nhẹ để học sinh tự sửa: tự kiểm tra, chỉ vùng cần xem lại, nhắc quy tắc."),
    A.CONCEPTUAL_QUESTION: ActionSpec(
        intents=frozenset({I.TARGET_MISCONCEPTION}), hint_levels=frozenset({0, 1, 2}),
        requires_target_skill=True, requires_evidence=True,
        summary="Câu hỏi khái niệm nhắm vào misconception có bằng chứng."),
    A.BACKTRACK: ActionSpec(
        intents=frozenset({I.REVIEW_PREREQUISITE}), hint_levels=frozenset({0, 1}),
        requires_target_skill=True, requires_evidence=True, requires_edges=True, requires_problem=True,
        summary="Quay lại prerequisite qua cạnh KG đã duyệt bằng một bài của concept nền; "
                "đẩy bài hiện tại vào return stack."),
    A.SCAFFOLD: ActionSpec(
        intents=frozenset({I.DECOMPOSE_STEP, I.ANALOGOUS_EXAMPLE, I.EXPLAIN_CONCEPT}),
        hint_levels=frozenset({3, 4}), requires_target_skill=True, requires_evidence=True,
        requires_content=True,
        summary="Chia nhỏ thao tác hoặc minh họa bằng bài khác; không giải bài đang làm."),
    A.CHECK_TRANSFER: ActionSpec(
        intents=frozenset({I.INDEPENDENT_CHECK}), hint_levels=frozenset({0}),
        requires_target_skill=True, requires_evidence=True, requires_problem=True,
        counts_as_assistance=False,
        summary="Bài mới không kèm hint để kiểm tra hiểu thật sau khi làm đúng có hỗ trợ."),
    A.NEXT_PROBLEM: ActionSpec(
        intents=frozenset({I.CONTINUE_PRACTICE, I.ADVANCE_DIFFICULTY, I.ADVANCE_CONCEPT,
                           I.RETURN_TO_PARENT, I.SWITCH_PROBLEM}),
        hint_levels=frozenset({0}), requires_target_skill=True, requires_evidence=True,
        requires_problem=True, counts_as_assistance=False,
        summary="Chuyển bài, tăng độ khó, chuyển concept hoặc quay lại bài trước khi backtrack."),
    A.END_SESSION: ActionSpec(
        intents=frozenset({I.STUDENT_REQUEST, I.SESSION_GOAL_MET, I.BUDGET_EXHAUSTED,
                           I.STUCK_LIMIT, I.CONTENT_EXHAUSTED, I.SYSTEM_FALLBACK}),
        hint_levels=frozenset({0}), requires_target_skill=False, requires_evidence=False,
        counts_as_assistance=False,
        summary="Kết thúc phiên hoặc dừng nhánh đang kẹt; tạm dừng không bị ghi thành câu trả lời sai."),
}

INTENT_ACTION: dict[DecisionIntent, PedagogicalAction] = {
    intent: action for action, spec in ACTION_SPECS.items() for intent in spec.intents
}

# Ưu tiên khi nhiều nhu cầu cùng xuất hiện (plan §9, PRD FR10-AC2): số nhỏ đứng trước.
ACTION_PRIORITY: dict[PedagogicalAction, int] = {
    A.CLARIFY: 0,
    A.DIAGNOSE: 1,
    A.MINIMAL_HINT: 2, A.CONCEPTUAL_QUESTION: 2, A.SCAFFOLD: 2, A.BACKTRACK: 2,
    A.CHECK_TRANSFER: 3,
    A.NEXT_PROBLEM: 4,
    A.END_SESSION: 5,
}

# Học sinh xin dừng hoặc hết ngân sách thì luôn được ưu tiên trước mọi nhu cầu sư phạm
# (plan §10: cho học sinh kết thúc; tạm dừng không bị ghi thành câu trả lời sai).
OVERRIDING_INTENTS = frozenset({I.STUDENT_REQUEST, I.BUDGET_EXHAUSTED})


def priority(action: PedagogicalAction, intent: DecisionIntent) -> int:
    return -1 if intent in OVERRIDING_INTENTS else ACTION_PRIORITY[action]


# ---------------------------------------------------------------------------
# Quyết định
# ---------------------------------------------------------------------------

class EvidenceKind(StrEnum):
    ASSESSMENT = "assessment"
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    STUDENT_MESSAGE = "student_message"
    DECISION = "decision"


class EvidenceRef(Contract):
    kind: EvidenceKind
    id: Annotated[str, Field(min_length=1, max_length=80)]


class DecisionProposal(Contract):
    """Đầu ra của Agent (hoặc Rule-policy) trước policy gate.

    Không có trường nào ghi mastery hay tham số BKT (PRD FR10-AC5); ``extra="forbid"`` chặn
    mọi trường lạ. ``reason`` là lý do ngắn kiểm tra được, không phải chuỗi suy nghĩ."""

    action: PedagogicalAction
    intent: DecisionIntent
    target_skill_id: Identifier | None = None
    hint_level: HintLevel = 0
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=10)
    content_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    edge_ids: list[Identifier] = Field(default_factory=list, max_length=4)
    problem_id: Identifier | None = None
    reason: ShortText

    @model_validator(mode="after")
    def _shape(self):
        problems = structural_violations(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def structural_violations(p: DecisionProposal) -> list[str]:
    """Trả mã lỗi hình dạng (S01–S09). Dùng lại được trong policy gate."""
    spec = ACTION_SPECS[p.action]
    out = []
    if p.intent not in spec.intents:
        out.append(f"S01_intent_not_allowed:{p.action}/{p.intent}")
    if p.hint_level not in spec.hint_levels:
        out.append(f"S02_hint_level_not_allowed:{p.action}/{p.hint_level}")
    if spec.requires_target_skill and p.target_skill_id is None:
        out.append("S03_target_skill_required")
    if spec.requires_evidence and not p.evidence:
        out.append("S04_evidence_required")
    if (spec.requires_edges or p.intent == I.PROBE_PREREQUISITE) and not p.edge_ids:
        out.append("S05_edge_ids_required")
    if spec.requires_problem and p.problem_id is None:
        out.append("S06_problem_id_required")
    if spec.requires_content and not p.content_ids:
        out.append("S07_content_ids_required")
    if p.action == A.END_SESSION and (p.target_skill_id or p.content_ids or p.edge_ids or p.problem_id):
        out.append("S08_end_session_has_payload")
    for name in ("content_ids", "edge_ids"):
        values = getattr(p, name)
        if len(values) != len(set(values)):
            out.append(f"S09_duplicate_{name}")
    return out


class DecisionSource(StrEnum):
    AGENT = "agent"
    RULE_POLICY = "rule_policy"
    FALLBACK = "fallback"


class GateResult(Contract):
    status: Literal["accepted", "rejected"]
    violated_rules: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list)
    gate_version: str

    @model_validator(mode="after")
    def _consistent(self):
        if (self.status == "rejected") != bool(self.violated_rules):
            raise ValueError("rejected gate must list violated_rules; accepted gate must not")
        return self


class ExperimentConfiguration(StrEnum):
    """Cấu hình trong plan §18.1 có sinh PedagogicalDecision. Socratic LLM baseline không có
    student model/policy nên không ghi decision theo hợp đồng này."""

    FULL = "full"
    NO_BKT = "no_bkt"
    HEURISTIC = "heuristic"
    NO_KG = "no_kg"
    NO_RAG = "no_rag"
    RULE_POLICY = "rule_policy"


class DecisionConfig(Contract):
    configuration: ExperimentConfiguration
    policy_version: str
    prompt_version: str | None = None
    model_id: str | None = None
    kb_version: str | None = None
    graph_version: str | None = None


FallbackReason = Literal["gate_rejected", "agent_timeout", "agent_schema_error", "agent_error",
                         "budget_exhausted"]


class AgentUsage(Contract):
    """Chi phí một lần gọi LLM để Agent đề xuất (plan §18: latency/cost cho RQ5).

    Ghi cả khi lần gọi lỗi (``error``): lượt đó vẫn tốn thời gian và có thể tốn token.
    ``model_id`` là tên model provider trả về (thường kèm ngày snapshot), không phải tên cấu hình.
    Số token để null khi provider không trả ``usage`` (timeout, lỗi mạng): không biết, khác với 0.
    ``cost_usd`` để null khi chưa biết số token hoặc model không có trong bảng giá ``price_version``."""

    model_id: Annotated[str, Field(min_length=1, max_length=80)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=40)]
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    price_version: str | None = None
    error: Annotated[str, Field(max_length=120)] | None = None

    @property
    def tokens_known(self) -> bool:
        return None not in (self.input_tokens, self.cached_input_tokens, self.output_tokens)

    @model_validator(mode="after")
    def _tokens(self):
        known = [self.input_tokens, self.cached_input_tokens, self.output_tokens]
        if any(v is None for v in known) and any(v is not None for v in known):
            raise ValueError("token counts are either all known or all null")
        if self.tokens_known and self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        if (self.cost_usd is None) != (self.price_version is None):
            raise ValueError("cost_usd and price_version go together")
        if self.cost_usd is not None and not self.tokens_known:
            raise ValueError("cost_usd needs known token counts")
        return self


class PedagogicalDecision(Contract):
    """Bản ghi một quyết định trong decision log: giữ cả đề xuất lẫn kết quả sau gate
    (PRD FR10-AC4, §6.4). Quyết định fallback cũng phải qua gate (``fallback_gate``)."""

    contract_version: ContractVersion = CONTRACT_VERSION
    decision_id: UUID
    session_id: UUID
    turn_id: UUID
    opportunity_id: UUID
    state_version: int = Field(ge=1)
    proposed_by: Literal[DecisionSource.AGENT, DecisionSource.RULE_POLICY]
    proposed: DecisionProposal | None
    gate: GateResult | None
    final: DecisionProposal
    final_source: DecisionSource
    fallback_reason: FallbackReason | None = None
    fallback_gate: GateResult | None = None
    tool_calls_used: int = Field(ge=0, le=MAX_TOOL_CALLS)
    tool_errors: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=5)
    # Cạnh prerequisite KG trả về trong lượt. Cạnh được dùng nằm ở ``final.edge_ids``; phần còn
    # lại là ứng viên bị bỏ (PRD FR08-AC2).
    candidate_edge_ids: list[Identifier] = Field(default_factory=list, max_length=MAX_CONTEXT_EDGES)
    kg_source: Literal["neo4j", "registry_file"] | None = None
    graph_version: str | None = None
    regenerations_used: int = Field(default=0, ge=0, le=MAX_REGENERATIONS)
    # Lần gọi LLM của Agent trong lượt; None khi đề xuất không đến từ LLM (Rule-policy, Agent giả).
    agent_usage: AgentUsage | None = None
    # Thời gian proposer → gate → fallback (gồm lần gọi LLM nếu có), đo cho mọi cấu hình để so sánh
    # với Rule-policy. None với bản ghi không tạo qua ``decide.run_decision``.
    decision_latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    # Phiên bản workflow LangGraph đã tạo bản ghi (``graph.WORKFLOW_VERSION``); None ngoài LangGraph.
    workflow_version: str | None = Field(default=None, max_length=40)
    config: DecisionConfig
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _trace(self):
        is_fallback = self.final_source == DecisionSource.FALLBACK
        if is_fallback != (self.fallback_reason is not None):
            raise ValueError("fallback_reason is required exactly when final_source is fallback")
        if is_fallback != (self.fallback_gate is not None):
            raise ValueError("fallback_gate is required exactly when final_source is fallback")
        if self.fallback_gate is not None and self.fallback_gate.status != "accepted":
            raise ValueError("fallback decision must pass the gate")
        if self.configuration_is_rule_policy and (
                self.proposed_by != DecisionSource.RULE_POLICY
                or self.fallback_reason in {"agent_timeout", "agent_schema_error", "agent_error"}):
            raise ValueError("rule_policy configuration cannot have agent proposals or agent failures")
        if self.agent_usage is not None and self.proposed_by != DecisionSource.AGENT:
            raise ValueError("agent_usage is only recorded for agent proposals")
        if self.proposed is None:
            if self.gate is not None or self.fallback_reason not in {
                    "agent_timeout", "agent_schema_error", "agent_error", "budget_exhausted"}:
                raise ValueError("missing proposal needs no gate and an agent/budget fallback_reason")
            return self
        if self.gate is None:
            raise ValueError("a proposal must go through the gate")
        if self.gate.status == "accepted":
            if is_fallback or self.final != self.proposed or self.final_source != self.proposed_by:
                raise ValueError("accepted proposal must be the final decision")
        elif self.fallback_reason != "gate_rejected":
            raise ValueError("rejected proposal must fall back with fallback_reason=gate_rejected")
        return self

    @property
    def configuration_is_rule_policy(self) -> bool:
        return self.config.configuration == ExperimentConfiguration.RULE_POLICY


# ---------------------------------------------------------------------------
# State mà Agent được đọc (bản nháp để chốt với Member 1)
# ---------------------------------------------------------------------------

AssessmentStatus = Literal["verified_correct", "verified_incorrect", "unverified", "needs_clarification"]


class CurrentTask(Contract):
    problem_id: Identifier
    problem_version: str
    opportunity_id: UUID
    concept_id: Identifier
    target_skill_id: Identifier
    template_family_id: Identifier
    relation: Literal["initial", "near_practice", "cross_family", "repeat", "prerequisite"]
    # Độ khó của bài đang làm (thang problem bank 1–5), để gate kiểm tra advance_difficulty.
    difficulty: int | None = Field(default=None, ge=1, le=5)


class AssessmentView(Contract):
    """Phần Agent cần từ Assessment của Member 1. Không chứa đáp án hay lời giải mẫu."""

    assessment_id: UUID
    assessment_status: AssessmentStatus
    first_error_step: int | None = Field(default=None, ge=1)
    primary_skill_id: Identifier | None = None
    error_family: Identifier | None = None
    misconception_candidate: Identifier | None = None
    diagnosis_status: Literal["suspected", "supported", "unknown"] = "unknown"
    final_answer_only: bool = False


class ObservationStatus(Contract):
    eligible: bool
    reason: Identifier
    observation_id: UUID | None = None


class SkillState(Contract):
    """``p_mastery`` để trống trong cấu hình No-BKT/Heuristic hoặc khi chưa có tham số.
    ``recent_independent`` là kết quả của tối đa 5 observation độc lập gần nhất, cũ trước mới sau
    (dùng cho cấu hình Heuristic, plan §18.1)."""

    skill_id: Identifier
    p_mastery: Probability | None = None
    independent_observations: int = Field(ge=0)
    recent_independent: list[bool] = Field(default_factory=list, max_length=5)
    assisted_correct: int = Field(default=0, ge=0)
    parameter_version: str | None = None


class Hypothesis(Contract):
    """Có ID riêng để ``EvidenceRef(kind="hypothesis")`` trỏ đúng một giả thuyết, kể cả khi
    cùng misconception xuất hiện ở hai skill."""

    hypothesis_id: Identifier
    misconception_id: Identifier
    skill_id: Identifier
    status: Literal["suspected", "supported", "ruled_out"]
    evidence_ids: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1)


class SupportState(Contract):
    hint_level: HintLevel = 0
    support_turns_on_node: int = Field(default=0, ge=0)
    no_progress_turns: int = Field(default=0, ge=0)


class ReturnFrame(Contract):
    problem_id: Identifier
    opportunity_id: UUID
    concept_id: Identifier
    skill_id: Identifier
    hint_level: HintLevel


class TurnSummary(Contract):
    turn_id: UUID
    actor: Literal["student", "tutor"]
    kind: Literal["submit", "request_hint", "message", "pause", "resume", "decision"]
    action: PedagogicalAction | None = None
    assessment_status: AssessmentStatus | None = None
    hint_level: HintLevel | None = None


class Budget(Contract):
    tool_calls_remaining: int = Field(default=MAX_TOOL_CALLS, ge=0, le=MAX_TOOL_CALLS)
    regenerations_remaining: int = Field(default=MAX_REGENERATIONS, ge=0, le=MAX_REGENERATIONS)


class Readiness(Contract):
    """Tính bằng node xác định (không phải Agent) theo điều kiện dừng plan §10."""

    ready_to_advance: bool
    criteria_version: str
    unmet: list[Identifier] = Field(default_factory=list)


MAX_PROBES = 6


class PrerequisiteProbe(Contract):
    """Một câu hỏi kiểm tra prerequisite đã hỏi trên bài hiện tại, gắn với lượt trả lời và kết
    quả xác minh câu trả lời đó (PRD FR08-AC3).

    - ``pending``: chưa có lượt trả lời (xin gợi ý, tạm dừng không tính là trả lời).
    - ``unverified``: có lượt sau đó nhưng không xác minh được, hoặc học sinh nộp bài thay vì trả lời.
    - ``demonstrated`` / ``not_demonstrated``: câu trả lời đã được xác minh.
    Chỉ ``not_demonstrated`` là bằng chứng học sinh thiếu skill nền; việc đã hỏi thì không."""

    decision_id: UUID
    skill_id: Identifier
    status: Literal["pending", "unverified", "demonstrated", "not_demonstrated"] = "pending"
    answer_turn_id: UUID | None = None

    @model_validator(mode="after")
    def _answer_link(self):
        if (self.status == "pending") != (self.answer_turn_id is None):
            raise ValueError("answer_turn_id is required exactly when the probe is no longer pending")
        return self


class StudentState(Contract):
    """Ảnh chụp state mà node Agent được đọc trong một lượt (PRD FR11-AC1, §6.4).

    ``latest_submission`` và ``latest_student_message`` là dữ liệu người dùng, không phải chỉ dẫn
    cho Agent. Hai trường tách riêng: bài làm là đúng các dòng analyzer đã chấm ra
    ``latest_assessment``; lời nhắn là chữ tự do của lượt này, có thể nói khác bài làm."""

    contract_version: ContractVersion = CONTRACT_VERSION
    student_id: Identifier
    session_id: UUID
    state_version: int = Field(ge=1)
    turn_id: UUID
    request_id: UUID
    status: Literal["active", "paused", "completed"]
    trigger: Literal["submit", "request_hint", "message", "pause", "resume"]
    # Lời nhắn tự do của học sinh trong lượt này (None nếu lượt không có tin nhắn).
    latest_student_message: str | None = Field(default=None, max_length=2000)
    # Bài làm của lần nộp gần nhất, đúng các dòng đã đưa cho analyzer; đi cùng latest_assessment
    # và bị xóa cùng nó khi đổi bài.
    latest_submission: list[SubmissionLine] = Field(default_factory=list, max_length=MAX_SUBMISSION_LINES)
    # Loại thông tin mastery mà policy được dùng (plan §18.1): "bkt" = P(L); "recent_ratio" =
    # tỷ lệ đúng ≤ 5 observation gần nhất (Heuristic); "none" = không có bản tóm tắt nào (No-BKT),
    # chỉ còn evidence log thô (recent_independent, số observation).
    mastery_view: Literal["bkt", "recent_ratio", "none"] = "bkt"
    current: CurrentTask
    latest_assessment: AssessmentView | None = None
    observation: ObservationStatus | None = None
    skills: list[SkillState] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    support: SupportState = Field(default_factory=SupportState)
    return_stack: list[ReturnFrame] = Field(default_factory=list, max_length=MAX_BACKTRACK_DEPTH)
    visited_concept_ids: list[Identifier] = Field(default_factory=list)
    # Bài đã giao trong phiên: tránh giao lại làm "bài mới" hoặc dùng làm bằng chứng chuyển giao.
    attempted_problem_ids: list[Identifier] = Field(default_factory=list)
    # Câu hỏi kiểm tra prerequisite trên bài hiện tại; xóa khi đổi bài. Tối đa một câu đang chờ.
    probes: list[PrerequisiteProbe] = Field(default_factory=list, max_length=MAX_PROBES)
    recent_turns: list[TurnSummary] = Field(default_factory=list, max_length=12)
    budget: Budget = Field(default_factory=Budget)
    readiness: Readiness

    @model_validator(mode="after")
    def _unique(self):
        skill_ids = [s.skill_id for s in self.skills]
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("skills must have unique skill_id")
        hypothesis_ids = [h.hypothesis_id for h in self.hypotheses]
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("hypotheses must have unique hypothesis_id")
        if sum(q.status == "pending" for q in self.probes) > 1:
            raise ValueError("at most one prerequisite probe can be pending")
        return self

    def skill(self, skill_id: str) -> SkillState | None:
        return next((s for s in self.skills if s.skill_id == skill_id), None)


EXPORTED_MODELS = (DecisionProposal, PedagogicalDecision, StudentState)
