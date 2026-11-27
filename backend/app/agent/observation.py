"""Observation và BKT thật: dùng ``app.knowledge`` của Member 1 (luật đủ điều kiện + cập nhật BKT).

Graph và replay bộ tình huống (``research/scenarios/replay.py``) cùng gọi ``observe_submission`` và
cùng ghi ``ObservationLedger``, nên state dựng lại từ lịch sử khớp với state hệ thống có khi chạy thật.

Đầu vào cho ``knowledge.eligibility`` được dựng theo đúng cách backend của Member 1 dựng
(``app/tutor_service.py: context`` và ``app/sessions.py: next_problem``):

- ``near``: trong phiên đã có **bài khác** cùng họ mẫu từng nhận trợ giúp. Cùng họ mà học sinh tự làm
  thì vẫn được xét ghi nhận. Nhãn ``near_practice`` của graph (chỉ nói hai bài cùng họ) không được
  dùng làm điều kiện. Backend còn xét cùng ``source_group``; problem bank mẫu chưa có trường này.
- ``first_attempt``: opportunity chưa có lần nộp nào chấm được (đúng hoặc sai). Lần nộp không đọc được
  hoặc chưa xác minh không tính, để học sinh viết lại rồi vẫn có lần thử độc lập đầu tiên.
- ``relation="repeat"``: quay lại bài cha (cùng opportunity, graph gán ``repeat``).
- Lỗi thuộc skill khác skill đích của bài (ví dụ lỗi phân phối A02 trong bài phương trình E02) không
  cập nhật skill nào (``not_target_evidence``).

Tham số BKT lấy theo skill qua ``parameters``. Mặc định là bộ khởi đầu ``content/bkt.bootstrap.v1.json``
dùng chung cho mọi skill: chưa fit, chỉ để chạy demo. Mastery tính bằng một phiên bản tham số không
được cập nhật tiếp bằng phiên bản khác (như ``persist_evidence`` của backend): đổi bộ tham số thì phải
tính lại từ lịch sử hoặc chuyển đổi tường minh.

Chưa lưu tiến độ học sinh vào cơ sở dữ liệu (``app/progress.py`` của Member 1 còn trống): mastery chỉ
nằm trong state của phiên.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app import knowledge
from app.agent.decision import (
    ACTION_SPECS, RECENT_INDEPENDENT_WINDOW, ObservationStatus, SkillState, StudentState,
)

# skill_id → {"parameter_version", "prior", "learn", "guess", "slip"}
ParametersFor = Callable[[str], dict]
# Không đủ điều kiện ghi observation nhưng vẫn là "làm đúng có hỗ trợ" (plan §8.3: sửa sau hint hoặc
# lặp cùng opportunity thì lưu kết quả có hỗ trợ).
ASSISTED_REASONS = frozenset({"already_observed", "assisted"})
VERIFIED = frozenset({"verified_correct", "verified_incorrect"})


class ParameterVersionMismatch(ValueError):
    """Mastery của skill được tính bằng bộ tham số khác bộ đang dùng."""


class LegacyCheckpoint(RuntimeError):
    """Checkpoint tạo trước khi có ``ObservationLedger`` (chỉ có ``observed_opportunities``). Không dựng
    lại được bài nào đã nhận trợ giúp, nên không tiếp tục phiên: phải mở phiên mới."""


def ledger_from_checkpoint(values: dict) -> "ObservationLedger":
    if values.get("observation_ledger") is not None:
        return ObservationLedger.model_validate(values["observation_ledger"])
    if "observed_opportunities" in values:
        raise LegacyCheckpoint("checkpoint predates the observation ledger; start a new session")
    return ObservationLedger()  # state nạp thẳng (ablation) hoặc phiên mới


class ObservationLedger(BaseModel):
    """Những gì luật ghi nhận cần biết về các opportunity trước đó trong phiên (lưu trong checkpoint)."""

    model_config = ConfigDict(frozen=True)

    # Opportunity đã có observation.
    observed: frozenset[str] = Field(default_factory=frozenset)
    # Opportunity đã có ít nhất một lần nộp chấm được (đúng hoặc sai).
    verified_attempts: frozenset[str] = Field(default_factory=frozenset)
    # Opportunity đã nhận trợ giúp → họ mẫu của bài đó.
    assisted: dict[str, str] = Field(default_factory=dict)

    def note_decision(self, state: StudentState, decision) -> "ObservationLedger":
        """Ghi trợ giúp cho bài mà quyết định đang xử lý. Gọi với state **trước** khi áp quyết định:
        backtrack hay chuyển bài đặt lại mức hỗ trợ, nên ghi sau đó sẽ mất dấu bài gốc. Graph (node
        commit), replay và công cụ soạn tình huống cùng gọi hàm này."""
        if not (assisted_now(state) or ACTION_SPECS[decision.action].counts_as_assistance):
            return self
        opportunity = str(state.current.opportunity_id)
        return self.model_copy(update={"assisted": {**self.assisted,
                                                    opportunity: state.current.template_family_id}})

    def assisted_family_elsewhere(self, state: StudentState) -> bool:
        current = str(state.current.opportunity_id)
        return any(family == state.current.template_family_id and opportunity != current
                   for opportunity, family in self.assisted.items())


def assisted_now(state: StudentState) -> bool:
    return state.support.hint_level > 0 or state.support.support_turns_on_node > 0


def bootstrap_parameters(skill_id: str) -> dict:
    """Bộ tham số khởi đầu của Member 1, dùng chung cho mọi skill."""
    p = knowledge.PARAMETERS
    return {key: p[key] for key in ("parameter_version", "prior", "learn", "guess", "slip")}


@dataclass(frozen=True)
class ObservationResult:
    status: ObservationStatus
    skills: list[SkillState]
    ledger: ObservationLedger
    observed_skill_id: str | None = None


@dataclass(frozen=True)
class ObservationTrace:
    """Số liệu BKT của một lần nộp bài, để kiểm tra và đánh giá (RQ1a)."""
    skill_id: str
    eligible: bool
    reason: str
    mastery_before: float | None
    mastery_after: float | None
    prediction_before: float | None = None


def observe_submission(state: StudentState, ledger: ObservationLedger,
                       parameters: ParametersFor = bootstrap_parameters, *,
                       target_evidence: bool = True) -> tuple[ObservationResult, ObservationTrace]:
    """Quyết định lần nộp vừa chấm có được ghi observation không và cập nhật BKT của skill đích.

    ``target_evidence=False``: bài chỉ chấm đáp án cuối (chế độ của Member 2), web trả
    ``not_target_evidence`` và không tạo observation (``tutor.outcome_eligibility``). Agent làm giống hệt:
    vẫn giữ kết quả chấm và lịch sử làm bài, nhưng không cập nhật BKT."""
    task, a = state.current, state.latest_assessment
    opportunity = str(task.opportunity_id)
    if not target_evidence:
        verdict = {"eligible": False, "reason": "not_target_evidence"}
    else:
        verdict = knowledge.eligibility(
            a.model_dump(),
            {"assistance_level": int(assisted_now(state)), "target_skill_id": task.target_skill_id,
             "relation": "repeat" if task.relation == "repeat" else "initial"},
            observed=opportunity in ledger.observed, near=ledger.assisted_family_elsewhere(state),
            first_attempt=opportunity not in ledger.verified_attempts)
    skills = {skill.skill_id: skill for skill in state.skills}
    params = parameters(task.target_skill_id)
    existing = skills.get(task.target_skill_id)
    if verdict["eligible"] and existing is not None and existing.parameter_version not in (
            None, params["parameter_version"]):
        raise ParameterVersionMismatch(
            f"{task.target_skill_id}: mastery from {existing.parameter_version}, parameters are "
            f"{params['parameter_version']}; recompute from history or convert explicitly")
    skill = existing or SkillState(skill_id=task.target_skill_id, p_mastery=params["prior"],
                                   independent_observations=0, parameter_version=params["parameter_version"])
    correct = a.assessment_status == "verified_correct"
    before = skill.p_mastery if skill.p_mastery is not None else params["prior"]
    prediction, observation_id = None, None
    if verdict["eligible"]:
        values = knowledge.update(before, correct, params)
        prediction = values["prediction_before"]
        skill = skill.model_copy(update={
            "p_mastery": values["mastery_after"],
            "independent_observations": skill.independent_observations + 1,
            "recent_independent": (skill.recent_independent + [correct])[-RECENT_INDEPENDENT_WINDOW:],
            "parameter_version": params["parameter_version"]})
        ledger = ledger.model_copy(update={"observed": ledger.observed | {opportunity}})
        observation_id = uuid5(NAMESPACE_URL, f"{state.student_id}:{opportunity}:{skill.skill_id}")
    elif correct and verdict["reason"] in ASSISTED_REASONS:
        skill = skill.model_copy(update={"assisted_correct": skill.assisted_correct + 1})
    elif existing is None:  # không ghi gì: không thêm skill rỗng vào state
        skill = None
    if skill is not None:
        skills[skill.skill_id] = skill
    if a.assessment_status in VERIFIED:
        ledger = ledger.model_copy(update={"verified_attempts": ledger.verified_attempts | {opportunity}})
    result = ObservationResult(ObservationStatus(**verdict, observation_id=observation_id), list(skills.values()),
                               ledger, task.target_skill_id if verdict["eligible"] else None)
    trace = ObservationTrace(task.target_skill_id, verdict["eligible"], verdict["reason"], before,
                             skill.p_mastery if skill is not None else before, prediction)
    return result, trace


@dataclass(frozen=True)
class KnowledgeObserver:
    """Observer cho graph. ``counts_as_evidence(problem_id)`` cho biết bài có được dùng làm bằng chứng BKT
    không (mặc định: có); bài chỉ chấm đáp án cuối thì không, như web."""
    parameters: ParametersFor = bootstrap_parameters
    counts_as_evidence: Callable[[str], bool] | None = None

    def __call__(self, state: StudentState, assessment, ledger: ObservationLedger) -> ObservationResult:
        evidence = self.counts_as_evidence is None or self.counts_as_evidence(state.current.problem_id)
        return observe_submission(state, ledger, self.parameters, target_evidence=evidence)[0]
