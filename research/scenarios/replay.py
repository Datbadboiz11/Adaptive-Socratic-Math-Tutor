"""Dựng StudentState từ lịch sử bằng chính các bước ghi state của graph (plan §11.5, §18.2).

Lượt của học sinh đi qua ``start_turn`` → ``record_student_turn`` → ``record_observation``; quyết
định của tutor đi qua ``finish_turn`` (``apply_decision``). Đó là các hàm mà node của graph gọi,
nên state dựng lại là state hệ thống có sau đúng lịch sử đó. Replay chỉ khác graph ở hai nguồn:

- Assessment lấy từ lịch sử thay cho analyzer.
- Tham số BKT lấy theo từng skill từ bộ dữ liệu; graph dùng bộ khởi đầu chung. Observation và BKT
  dùng cùng hàm ``app.agent.observation.observe_submission`` với graph (xem ``observe``).

Replay không tin ``task`` của sự kiện: bài chỉ đổi qua quyết định của tutor, và ``task`` phải khớp
với bài mà state đang giữ (kể cả ``relation`` do graph gán).

``apply_decision`` ghi state với giả định quyết định đã qua policy gate: mọi ``check_transfer`` được
ghi là bài khác họ mẫu, mọi backtrack là đi xuống một prerequisite. Vì vậy quyết định giao bài trong
lịch sử phải qua đúng các luật chuyển bài của gate (``TRANSITION_RULES``) trước khi được áp.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from app.agent.decision import (
    DecisionIntent, DecisionProposal, ObservationStatus, PedagogicalAction, Readiness, SkillState, StudentState,
)
from app.agent.gate import gate_violations
from app.agent.graph import (
    Services, TurnInput, finish_turn, record_observation, record_student_turn, start_turn, task_for,
)
from app.agent.kg_tool import KGLookup, KGTool
from app.agent.rule_policy import READINESS_VERSION, compute_readiness
from app.agent.observation import ObservationLedger, ObservationResult, observe_submission
from app.agent.tools import ProblemRef, TurnContext
from research.scenarios.contracts import BKTParameters, HistoryEvent, ReplayRecord, ScenarioDataset, ScenarioDraft

A, I = PedagogicalAction, DecisionIntent
REPLAY_VERSION = "scenario-replay-2.1.0"
# Luật của policy gate quyết định một bài mới có được giao hay không: bài thuộc problem bank và đúng
# skill, chưa giao trong phiên (G13); check_transfer sang họ mẫu khác (G12); luyện tiếp trong cùng
# concept/skill và tăng độ khó thật (G20); chuyển concept theo cạnh KG (G19); backtrack xuống một
# prerequisite trực tiếp, không lặp vòng, tối đa hai tầng (G05, G08); quay lại đúng bài cha (G09).
# Các luật còn lại của gate xét quyết định có hợp lý về sư phạm không (ví dụ có đủ bằng chứng để
# backtrack), không đổi cách state được ghi, và cần những trường lịch sử không lưu (evidence, nội dung).
TRANSITION_RULES = ("G05_", "G08_backtrack_depth", "G08_backtrack_loop", "G08_backtrack_one_level_per_step",
                    "G09_", "G12_", "G13_", "G19_", "G20_")


def replay(draft: ScenarioDraft, dataset: ScenarioDataset,
           kg: Callable[[str], KGLookup] | None = None) -> tuple[StudentState, list[ReplayRecord]]:
    """State ngay trước quyết định cần đánh giá, và dấu vết observation của từng lần nộp bài.

    ``kg`` trả cạnh prerequisite và concept kế tiếp của một concept, để kiểm tra backtrack và chuyển
    concept; mặc định đọc registry kể cả cạnh nháp, như chế độ dev của hệ thống."""
    kg = kg or KGTool(include_drafts=True)
    problems = {p.problem.problem_id: p.problem for p in dataset.problems}
    events = _unique_events(draft)
    state = _initial_state(draft, dataset, events[0], problems)
    services = Services(problem_ref=problems.__getitem__)
    no_evidence = frozenset(p.problem.problem_id for p in dataset.problems if not p.target_evidence)
    ledger = ObservationLedger()
    opportunities = {state.current.opportunity_id}
    trace: list[ReplayRecord] = []
    for index, event in enumerate(events):
        where = f"{draft.scenario_id} event {index + 1}"
        if event.task != state.current:
            raise ValueError(f"{where}: task differs from the task the system holds here "
                             f"({state.current.model_dump_json()})")
        if event.task.target_skill_id not in dataset.parameters:
            raise ValueError(f"{where}: missing explicit BKT parameters for {event.task.target_skill_id}")
        if index and event.actor == events[index - 1].actor:
            raise ValueError(f"{where}: student turns and tutor decisions must alternate")
        if event.actor == "student":
            state, ledger = _student_turn(state, event, services, ledger, dataset.parameters, trace, where,
                                          no_evidence)
            continue
        state, ledger = _tutor_turn(state, ledger, event, events[index + 1], services, problems, kg, where)
        assigns_new_task = event.problem_id is not None and event.intent != I.RETURN_TO_PARENT
        if assigns_new_task and state.current.opportunity_id in opportunities:
            raise ValueError(f"{where}: a new task cannot reuse an earlier opportunity_id")
        opportunities.add(state.current.opportunity_id)
    return state.model_copy(update={"readiness": compute_readiness(state)}), trace


def _unique_events(draft: ScenarioDraft) -> list[HistoryEvent]:
    """Lịch sử sau khi bỏ request gửi lại (FR-11: mỗi request xử lý đúng một lần)."""
    seen: dict[str, HistoryEvent] = {}
    for event in draft.history:
        first = seen.setdefault(str(event.request_id), event)
        if first != event:
            raise ValueError(f"{draft.scenario_id}: conflicting duplicate request {event.request_id}")
    events = list(seen.values())
    for name, ids in (("turn_id", [e.turn_id for e in events]),
                      ("assessment_id", [e.assessment.assessment_id for e in events if e.assessment])):
        if len(ids) != len(set(ids)):
            raise ValueError(f"{draft.scenario_id}: {name} reused by another event")
    if events[-1].actor != "student":
        raise ValueError(f"{draft.scenario_id}: history must end with a student turn")
    return events


def _initial_state(draft: ScenarioDraft, dataset: ScenarioDataset, first: HistoryEvent,
                   problems: dict[str, ProblemRef]) -> StudentState:
    """State lúc mở phiên, như ``TutorEngine.start``; mỗi skill bắt đầu từ prior đã khai báo."""
    ref = problems.get(first.task.problem_id)
    if first.actor != "student":
        raise ValueError(f"{draft.scenario_id}: history must start with a student turn")
    if ref is None or first.task != task_for(ref, first.task.opportunity_id, first.task.relation):
        raise ValueError(f"{draft.scenario_id}: first task does not match the problem catalogue")
    if first.task.relation == "prerequisite":
        raise ValueError(f"{draft.scenario_id}: a history cannot start inside a prerequisite branch")
    skills = [_new_skill(skill_id, p) for skill_id, p in dataset.parameters.items()]
    return StudentState(
        student_id=draft.student_id, session_id=draft.session_id, state_version=1, turn_id=first.turn_id,
        request_id=first.request_id, status="active", trigger="resume", current=first.task, skills=skills,
        visited_concept_ids=[first.task.concept_id],
        readiness=Readiness(ready_to_advance=False, criteria_version=READINESS_VERSION,
                            unmet=["too_few_observations"]))


def _new_skill(skill_id: str, p: BKTParameters) -> SkillState:
    return SkillState(skill_id=skill_id, p_mastery=p.prior, independent_observations=0,
                      parameter_version=p.parameter_version)


def _student_turn(state: StudentState, event: HistoryEvent, services: Services, ledger: ObservationLedger,
                  parameters: dict[str, BKTParameters], trace: list[ReplayRecord],
                  where: str, no_evidence: frozenset[str] = frozenset()) -> tuple[StudentState, ObservationLedger]:
    """``no_evidence``: bài không tạo observation BKT (``ProblemSource.target_evidence``)."""
    if state.status == "completed" or (state.status == "paused" and event.kind != "resume"):
        raise ValueError(f"{where}: session is {state.status}; this turn cannot happen")
    turn = TurnInput(request_id=event.request_id, trigger=event.kind, steps=event.submission, message=event.message)
    state = start_turn(state, turn, event.turn_id)
    state = record_student_turn(state, turn, services, event.assessment, event.submission)
    if event.assessment is None:
        return state, ledger
    result, record = observe(state, ledger, parameters,
                             target_evidence=state.current.problem_id not in no_evidence)
    trace.append(record)
    return record_observation(state, result), result.ledger


def observe(state: StudentState, ledger: ObservationLedger, parameters: dict[str, BKTParameters], *,
            target_evidence: bool = True) -> tuple[ObservationResult, ReplayRecord]:
    """Observation và BKT cho lần nộp vừa chấm: đúng hàm graph dùng (``observe_submission``), chỉ khác
    tham số BKT lấy theo từng skill từ bộ dữ liệu."""
    result, t = observe_submission(state, ledger, lambda skill_id: parameters[skill_id].model_dump(),
                                   target_evidence=target_evidence)
    return result, ReplayRecord(turn_id=state.turn_id, skill_id=t.skill_id, prediction_before=t.prediction_before,
                                mastery_before=t.mastery_before, mastery_after=t.mastery_after,
                                eligible=t.eligible, reason=t.reason)


def _tutor_turn(state: StudentState, ledger: ObservationLedger, event: HistoryEvent, upcoming: HistoryEvent,
                services: Services, problems: dict[str, ProblemRef], kg: Callable[[str], KGLookup],
                where: str) -> tuple[StudentState, ObservationLedger]:
    """Áp quyết định đã ghi trong lịch sử, sau khi các luật chuyển bài của gate cho qua. Bài mới nhận
    ``opportunity_id`` mà lượt kế tiếp ghi. Trợ giúp được ghi vào sổ trước khi áp, như node commit."""
    context, edge_ids = TurnContext(), []
    if event.problem_id is not None:
        assigned = problems.get(event.problem_id)
        if assigned is None:
            raise ValueError(f"{where}: decision assigns a problem outside the catalogue")
        found = kg(state.current.concept_id)
        context = TurnContext(problems=[assigned], edges=found.edges, next_concepts=found.next_concepts)
        # Lịch sử không ghi edge_ids: cạnh mà quyết định phải đi theo được tìm trong registry.
        if event.action == A.BACKTRACK:
            edge_ids = [e.edge_id for e in found.edges if e.depth == 1 and e.source_concept_id == assigned.concept_id]
            if not edge_ids:
                raise ValueError(f"{where}: {assigned.concept_id} is not a direct prerequisite of "
                                 f"{state.current.concept_id} in the registry")
        elif event.intent == I.ADVANCE_CONCEPT:
            edge_ids = [n.edge_id for n in found.next_concepts if n.concept_id == assigned.concept_id]
    # Lịch sử chỉ ghi phần quyết định có tác động lên state, nên không dựng được DecisionProposal đủ
    # trường (evidence, reason); gate và apply_decision chỉ đọc các trường có ở đây.
    decision = DecisionProposal.model_construct(
        action=event.action, intent=event.intent, hint_level=event.hint_level, problem_id=event.problem_id,
        target_skill_id=event.target_skill_id, edge_ids=edge_ids)
    broken = [rule for rule in gate_violations(state, decision, context) if rule.startswith(TRANSITION_RULES)]
    if broken:
        raise ValueError(f"{where}: the policy gate does not let the system make this decision here "
                         f"({', '.join(broken)})")
    ledger = ledger.note_decision(state, decision)
    return finish_turn(state, decision, replace(services, new_id=lambda: upcoming.task.opportunity_id),
                       event.turn_id), ledger
