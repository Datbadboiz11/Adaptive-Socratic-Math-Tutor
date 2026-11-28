"""Hợp đồng nghiên cứu cho lịch sử, nhãn và tình huống đã replay."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.agent.decision import (
    ACTION_SPECS, INTENT_ACTION, AssessmentView, Contract, CurrentTask, DecisionIntent, HintLevel, Identifier,
    PedagogicalAction, Probability, StudentState, SubmissionLine,
)
from app.agent.tools import ProblemRef, TurnContext

Split = Literal["authoring", "dev", "test"]


class BKTParameters(Contract):
    parameter_version: Identifier
    source: str = Field(min_length=1)
    prior: Probability
    learn: Probability
    guess: Probability
    slip: Probability
    forget: Literal[0] = 0

    @model_validator(mode="after")
    def distinguishable(self):
        if self.guess >= 1 - self.slip:
            raise ValueError("guess must be less than 1 - slip")
        return self


class ProblemSource(Contract):
    problem: ProblemRef
    original_problem_id: Identifier
    prompt: str = Field(min_length=1, max_length=1000)
    # False: bài chỉ chấm đáp án cuối (Member 2). Hệ thống không tạo observation BKT từ bài này
    # (``not_target_evidence``, giống web), nên replay cũng không.
    target_evidence: bool = True


class HistoryEvent(Contract):
    """Một sự kiện của phiên; thứ tự trong danh sách là thứ tự xảy ra. Lượt của học sinh và quyết
    định của tutor xen kẽ nhau như trong hệ thống.

    ``task`` là bài mà hệ thống đang giữ lúc sự kiện xảy ra. Bài chỉ đổi qua quyết định của tutor,
    nên replay kiểm tra ``task`` chứ không tin nó.

    Quyết định của tutor chỉ ghi phần có tác động lên state (``graph.apply_decision``): action,
    intent, mức hint, bài được giao cùng skill của nó, và skill được hỏi khi kiểm tra prerequisite.
    Quyết định giao bài phải qua các luật chuyển bài của policy gate. Assessment do validator hoặc người biên soạn
    cung cấp. Giả thuyết lỗi không ghi ở đây: replay suy ra từ ``misconception_candidate`` của
    assessment như hệ thống."""

    turn_id: UUID
    request_id: UUID
    task: CurrentTask
    actor: Literal["student", "tutor"]
    kind: Literal["submit", "request_hint", "message", "pause", "resume", "decision"]
    submission: list[SubmissionLine] = Field(default_factory=list, max_length=12)
    message: str | None = Field(default=None, max_length=2000)
    assessment: AssessmentView | None = None
    action: PedagogicalAction | None = None
    intent: DecisionIntent | None = None
    hint_level: HintLevel | None = None
    problem_id: Identifier | None = None
    target_skill_id: Identifier | None = None

    @model_validator(mode="after")
    def payload(self):
        decision = (self.action, self.intent, self.hint_level, self.problem_id, self.target_skill_id)
        if self.actor == "tutor":
            if self.kind != "decision" or None in decision[:3]:
                raise ValueError("Tutor event needs decision, action, intent and hint_level")
            if self.assessment or self.submission:
                raise ValueError("Tutor cannot submit work or an assessment")
            spec = ACTION_SPECS[self.action]
            if self.intent not in spec.intents or self.hint_level not in spec.hint_levels:
                raise ValueError(f"{self.action}/{self.intent} at hint level {self.hint_level} is not a valid decision")
            if spec.requires_problem != (self.problem_id is not None):
                raise ValueError(f"{self.action} needs problem_id exactly when it assigns a problem")
            names_skill = spec.requires_problem or self.intent == DecisionIntent.PROBE_PREREQUISITE
            if names_skill and self.target_skill_id is None:
                raise ValueError("A decision that assigns a problem or probes a prerequisite needs target_skill_id")
        else:
            if self.kind == "decision" or any(value is not None for value in decision):
                raise ValueError("Student event cannot carry a pedagogical decision")
            if self.kind == "submit":
                if not self.submission or self.assessment is None:
                    raise ValueError("Submit needs original work and an assessment")
            elif self.assessment or self.submission:
                raise ValueError("Only submit may contain work or an assessment")
        if self.assessment:
            a = self.assessment
            if a.first_error_step is not None and (
                    a.assessment_status != "verified_incorrect" or a.first_error_step > len(self.submission)):
                raise ValueError("First error must reference an incorrect submitted step")
            if a.final_answer_only and a.first_error_step is not None:
                raise ValueError("A final answer alone cannot establish the first wrong step")
        return self


def _check_label_shape(acceptable: list[PedagogicalAction], forbidden: list[PedagogicalAction],
                       intents: list[DecisionIntent]) -> None:
    if set(acceptable) & set(forbidden):
        raise ValueError("Acceptable and forbidden actions overlap")
    if len(intents) != len(set(intents)):
        raise ValueError("Duplicate acceptable intents")
    if stray := [i.value for i in intents if INTENT_ACTION[i] not in acceptable]:
        raise ValueError(f"Acceptable intents belong to actions that are not acceptable: {stray}")


class RaterLabel(Contract):
    """Nhãn một người gán độc lập, trước khi hòa giải (plan §12: lưu nhãn ban đầu)."""

    rater: Identifier
    acceptable_actions: list[PedagogicalAction] = Field(min_length=1)
    forbidden_actions: list[PedagogicalAction] = Field(default_factory=list)
    acceptable_intents: list[DecisionIntent] = Field(default_factory=list)
    acceptable_target_skill_ids: list[Identifier] = Field(default_factory=list)
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def shape(self):
        _check_label_shape(self.acceptable_actions, self.forbidden_actions, self.acceptable_intents)
        return self


class StrategyLabels(Contract):
    """Nhãn chiến lược cuối của một tình huống.

    ``acceptable_intents`` và ``acceptable_target_skill_ids`` dành cho ca mà action chưa đủ phân biệt
    (ví dụ ``next_problem`` vừa là luyện tiếp vừa là chuyển concept). Để trống là không ràng buộc.
    Action nào có ít nhất một intent được liệt kê thì chỉ các intent đó được chấp nhận; action không
    có intent nào được liệt kê thì nhận mọi intent của nó.

    ``independent_labels`` giữ nhãn ban đầu của từng người; các trường ở trên là nhãn cuối sau hòa
    giải. ``adjudicated`` cần ít nhất hai người gán nhãn độc lập (plan §12, bắt buộc với test)."""

    acceptable_actions: list[PedagogicalAction] = Field(min_length=1)
    forbidden_actions: list[PedagogicalAction] = Field(default_factory=list)
    acceptable_intents: list[DecisionIntent] = Field(default_factory=list)
    acceptable_target_skill_ids: list[Identifier] = Field(default_factory=list)
    review_status: Literal["draft", "human_approved", "adjudicated"] = "draft"
    author: Identifier
    reviewer: Identifier | None = None
    rationale: str = Field(min_length=1)
    independent_labels: list[RaterLabel] = Field(default_factory=list)
    adjudication_note: str | None = None

    @model_validator(mode="after")
    def reviewed_independently(self):
        _check_label_shape(self.acceptable_actions, self.forbidden_actions, self.acceptable_intents)
        if self.review_status == "human_approved" and (not self.reviewer or self.reviewer == self.author):
            raise ValueError("Approval needs a reviewer other than the label author")
        raters = [label.rater for label in self.independent_labels]
        if len(raters) != len(set(raters)):
            raise ValueError("Each rater labels a scenario once")
        if self.review_status == "adjudicated" and len(raters) < 2:
            raise ValueError("Adjudicated labels need at least two independent raters")
        return self

    def accepts(self, action: str, intent: str | None, target_skill_id: str | None) -> bool:
        """Quyết định có khớp nhãn ở mức chi tiết không: action, rồi intent và skill nếu nhãn có ràng buộc."""
        if action not in self.acceptable_actions:
            return False
        listed = [i for i in self.acceptable_intents if INTENT_ACTION[i] == action]
        if listed and intent not in listed:
            return False
        return not self.acceptable_target_skill_ids or target_skill_id in self.acceptable_target_skill_ids

    @property
    def has_detail(self) -> bool:
        return bool(self.acceptable_intents or self.acceptable_target_skill_ids)


class ScenarioDraft(Contract):
    """``context`` do người biên soạn cung cấp, trừ phần KG: ``build`` lấy cạnh prerequisite và
    concept kế tiếp từ registry, nên ``edges`` và ``next_concepts`` để trống.

    ``labels`` chỉ được để trống ở ca test: nhãn test do hai người gán độc lập sau khi dựng xong tình
    huống (plan §12), nên người dựng không viết nhãn. ``build`` từ chối ca chưa có nhãn."""

    scenario_id: Identifier
    title: str = Field(min_length=1)
    student_id: Identifier
    session_id: UUID
    history_group_id: Identifier
    source: Literal["synthetic_authoring", "student_real", "student_simulated"]
    source_reference: str = Field(min_length=1)
    split: Split | None = None
    tags: list[Identifier] = Field(min_length=1)
    history: list[HistoryEvent] = Field(min_length=1)
    context: TurnContext
    labels: StrategyLabels | None = None

    @model_validator(mode="after")
    def ends_at_student_turn(self):
        if self.history[-1].actor != "student":
            raise ValueError("Scenario must end before the tutor decision being evaluated")
        if self.labels is None and self.split != "test":
            raise ValueError("Only test scenarios may wait for labels")
        return self


class ScenarioDataset(Contract):
    schema_version: Literal["adaptive-scenarios-2.1.0"] = "adaptive-scenarios-2.1.0"
    dataset_version: Identifier
    parameters: dict[Identifier, BKTParameters]
    problems: list[ProblemSource] = Field(min_length=1)
    scenarios: list[ScenarioDraft] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        for ids in ([p.problem.problem_id for p in self.problems], [s.scenario_id for s in self.scenarios]):
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate problem or scenario IDs")
        return self


class ReplayRecord(Contract):
    turn_id: UUID
    skill_id: Identifier
    eligible: bool
    reason: Identifier
    prediction_before: Probability | None = None
    mastery_before: Probability
    mastery_after: Probability


class BuiltScenario(Contract):
    scenario_id: Identifier
    title: str
    split_group_id: Identifier
    source: str
    source_reference: str
    tags: list[Identifier]
    labels: StrategyLabels
    state: StudentState
    context: TurnContext
    replay: list[ReplayRecord]


class ScenarioSet(Contract):
    schema_version: Literal["adaptive-scenario-set-2.1.0"] = "adaptive-scenario-set-2.1.0"
    dataset_version: Identifier
    split: Split
    replay_version: str
    parameters: dict[Identifier, BKTParameters]
    problems: list[ProblemSource]
    scenarios: list[BuiltScenario]


EXPORTED_MODELS = (ScenarioDataset, ScenarioSet)
