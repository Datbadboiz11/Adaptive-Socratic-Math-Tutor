"""Khung LangGraph cho một lượt dạy (plan §7, §13; PRD FR-11).

    load → extract → analyze → observe → readiness → context → decide → generate → verify → commit

Mỗi lần ``invoke`` xử lý đúng một lượt rồi dừng; state của phiên nằm trong checkpointer theo
``thread_id = session_id``, nên dừng/tiếp tục hay khởi động lại tiến trình đều đọc lại được.
Request trùng ``request_id`` dừng ngay ở ``load``, không chấm hay cập nhật BKT lần hai.

Các phần của Member 1/2 được truyền vào qua ``Services``; hiện dùng stub trong ``stubs.py``.
``proposer`` mặc định là Rule-policy để chạy không cần API; Agent LLM là ``llm_proposer.LLMProposer``
(chọn theo cấu hình bằng ``llm_proposer.build_proposer``).
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Callable, Literal, Protocol, TypedDict
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import Field, model_validator

from app.agent.decide import ProposalOutcome, RulePolicyProposer, run_decision
from app.agent.decision import (
    ACTION_SPECS, CONTRACT_VERSION, MAX_PROBES, MAX_SUBMISSION_LINE_LENGTH, MAX_SUBMISSION_LINES,
    AssessmentView, Contract, CurrentTask, DecisionConfig, DecisionIntent, DecisionProposal,
    ExperimentConfiguration, HintLevel, Hypothesis, Identifier, PedagogicalAction, PedagogicalDecision,
    PrerequisiteProbe, Readiness, ReturnFrame, StudentState, SubmissionLine, SupportState, TurnSummary,
)
from app.agent.rule_policy import READINESS_VERSION, compute_readiness
from app.agent.stubs import (
    AnswerLeakVerifier, ObservationResult, StubAnalyzer, StubTools, TemplateGenerator, problem_prompt,
    problem_ref, stub_observe, unverified_probe,
)
from app.agent.tools import ProblemRef, TurnContext
from app.extraction.contracts import ExtractionRecord
from app.extraction.extractor import ExtractionOutcome, StepExtractor

A, I = PedagogicalAction, DecisionIntent
# Phiên bản workflow (thứ tự node và tác động của commit). Ghi vào từng PedagogicalDecision để truy
# được bản ghi nào sinh ra từ workflow nào (NFR-04). Đổi luồng hoặc apply_decision thì tăng.
WORKFLOW_VERSION = "tutor-graph-0.4.0"
MAX_RECENT_TURNS = 12
PAUSING_INTENTS = frozenset({I.STUDENT_REQUEST, I.STUCK_LIMIT, I.SYSTEM_FALLBACK, I.BUDGET_EXHAUSTED,
                             I.CONTENT_EXHAUSTED})


# --------------------------------------------------------------------------- contracts vào/ra

class TurnInput(Contract):
    """Một lượt từ UI. Khi nộp bài, bài làm là ``steps``; không có ``steps`` thì lấy từng dòng của
    ``message``. ``message`` còn là lời nhắn tự do và được giữ riêng, kể cả khi có ``steps``."""

    request_id: UUID
    trigger: Literal["submit", "request_hint", "message", "pause", "resume"]
    steps: list[SubmissionLine] = Field(default_factory=list, max_length=MAX_SUBMISSION_LINES)
    message: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _submission_fits(self):
        if self.trigger == "submit" and not self.steps:
            lines = self._message_lines()
            if len(lines) > MAX_SUBMISSION_LINES or any(len(x) > MAX_SUBMISSION_LINE_LENGTH for x in lines):
                raise ValueError(f"a submission has at most {MAX_SUBMISSION_LINES} lines of "
                                 f"{MAX_SUBMISSION_LINE_LENGTH} characters")
        return self

    def _message_lines(self) -> list[str]:
        return [line.strip() for line in (self.message or "").splitlines() if line.strip()]

    @property
    def submission(self) -> list[str]:
        """Đúng các dòng được đưa cho analyzer; rỗng nếu lượt này không nộp bài."""
        if self.trigger != "submit":
            return []
        return list(self.steps) or self._message_lines()


class TutorReply(Contract):
    """Phản hồi gửi UI (bản nháp để chốt với Member 2)."""

    contract_version: Literal["agent-contract-0.1.0"] = CONTRACT_VERSION
    session_id: UUID
    state_version: int = Field(ge=1)
    decision_id: UUID | None = None
    action: PedagogicalAction | None = None
    intent: DecisionIntent | None = None
    hint_level: HintLevel = 0
    message: str = Field(min_length=1, max_length=2000)
    response_source: Literal["template", "template_fallback", "llm", "system"]
    problem_id: Identifier
    problem_prompt: str | None = None
    status: Literal["active", "paused", "completed"]
    next_actions: list[Literal["submit", "request_hint", "pause", "resume"]]
    duplicate: bool = False


class SessionClosed(RuntimeError):
    pass


class TurnInProgress(RuntimeError):
    """Lượt trước bị lỗi giữa chừng. Client phải gửi lại đúng request đó để chạy tiếp
    (API trả 409); không nhận request mới khi state còn dở dang."""

    def __init__(self, pending_request_id: str):
        super().__init__(f"turn {pending_request_id} is incomplete; retry that request first")
        self.pending_request_id = pending_request_id


@dataclass
class Services:
    analyzer: Callable[[StudentState, list[str]], object] = field(default_factory=StubAnalyzer)
    observer: Callable[[StudentState, object, frozenset[str]], ObservationResult] = stub_observe
    tools: Callable[[StudentState, DecisionConfig], TurnContext] = field(default_factory=StubTools)
    # Tách bài làm tự do thành các bước trước khi chấm (LLM extraction). None: đưa thẳng bài làm cho
    # analyzer. Chỉ áp cho concept mà extractor hỗ trợ (``applies_to``).
    extractor: StepExtractor | None = None
    proposer: Callable[[StudentState, TurnContext], ProposalOutcome] = field(default_factory=RulePolicyProposer)
    generator: TemplateGenerator = field(default_factory=TemplateGenerator)
    verifier: Callable[[StudentState, DecisionProposal, str], list[str]] = field(default_factory=AnswerLeakVerifier)
    # Xác minh câu trả lời cho câu hỏi kiểm tra prerequisite: trả "demonstrated", "not_demonstrated"
    # hoặc "unverified". Bản thật sẽ là LLM extraction; stub luôn trả "unverified".
    probe_checker: Callable[[StudentState, PrerequisiteProbe, str], str] = unverified_probe
    problem_ref: Callable[[str], ProblemRef] = problem_ref
    problem_prompt: Callable[[str], str | None] = problem_prompt
    new_id: Callable[[], UUID] = uuid4
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


class TutorGraphState(TypedDict, total=False):
    student: dict
    turn_input: dict
    observed_opportunities: list[str]
    context: dict
    decision: dict
    message: str
    response_source: str
    reply: dict
    # request_id → phản hồi đã gửi. Giữ mọi request của phiên để request cũ gửi lại (kể cả sau
    # khi đã có lượt khác xen giữa) nhận đúng phản hồi cũ thay vì bị xử lý lại.
    processed: dict[str, dict]
    decision_log: list[dict]
    extraction_log: list[dict]
    # Kết quả extraction của lượt đang xử lý (ExtractionRecord) hoặc None. Node extract lưu nó vào
    # checkpoint trước khi analyzer chạy: analyzer lỗi rồi gửi lại thì dùng lại, không gọi LLM lần hai.
    extraction: dict | None
    duplicate: bool


# --------------------------------------------------------------------------- helpers

def project_state(s: StudentState, config: DecisionConfig) -> StudentState:
    """Phần state mà policy được thấy theo cấu hình ablation (plan §18.1)."""
    views = {ExperimentConfiguration.NO_BKT: "none", ExperimentConfiguration.HEURISTIC: "recent_ratio"}
    view = views.get(config.configuration)
    if view is None:
        return s
    return s.model_copy(update={"mastery_view": view,
                                "skills": [k.model_copy(update={"p_mastery": None}) for k in s.skills]})


def _turns(s: StudentState, *new: TurnSummary) -> list[TurnSummary]:
    return (list(s.recent_turns) + list(new))[-MAX_RECENT_TURNS:]


def _track_hypotheses(s: StudentState) -> list[Hypothesis]:
    a = s.latest_assessment
    hypotheses = list(s.hypotheses)
    if a is None or a.assessment_status != "verified_incorrect" or not a.misconception_candidate:
        return hypotheses
    skill = a.primary_skill_id or s.current.target_skill_id
    for i, h in enumerate(hypotheses):
        if h.misconception_id == a.misconception_candidate and h.skill_id == skill and h.status != "ruled_out":
            evidence = h.evidence_ids + [str(a.assessment_id)]
            hypotheses[i] = h.model_copy(update={"evidence_ids": evidence,
                                                 "status": "supported" if len(evidence) >= 2 else h.status})
            return hypotheses
    hypotheses.append(Hypothesis(hypothesis_id=f"HYP-{len(hypotheses) + 1:03d}",
                                 misconception_id=a.misconception_candidate, skill_id=skill,
                                 status="suspected", evidence_ids=[str(a.assessment_id)]))
    return hypotheses


def _answer_probe(s: StudentState, turn: "TurnInput", services: "Services") -> list[PrerequisiteProbe]:
    """Gắn lượt này với câu hỏi kiểm tra prerequisite đang chờ. Chỉ tin nhắn mới là câu trả lời và
    được đem đi xác minh; nộp bài nghĩa là học sinh làm tiếp mà không trả lời. Xin gợi ý, tạm dừng
    hay tiếp tục không trả lời gì nên câu hỏi vẫn chờ."""
    if turn.trigger not in {"submit", "message"}:
        return s.probes
    out = []
    for probe in s.probes:
        if probe.status == "pending":
            status = "unverified"
            if turn.trigger == "message":
                try:
                    status = services.probe_checker(s, probe, turn.message or "")
                except Exception:  # bộ xác minh lỗi thì coi như chưa xác minh được
                    status = "unverified"
            probe = PrerequisiteProbe(decision_id=probe.decision_id, skill_id=probe.skill_id,
                                      status="unverified" if status == "pending" else status,
                                      answer_turn_id=s.turn_id)
        out.append(probe)
    return out


def _extract(s: StudentState, submission: list[str], services: "Services") -> ExtractionOutcome | None:
    """Chạy extraction nếu được bật và concept đang học nằm trong phạm vi của nó."""
    extractor = services.extractor
    if extractor is None or not extractor.applies_to(s.current.concept_id):
        return None
    return extractor(services.problem_prompt(s.current.problem_id), submission)


def _task(ref: ProblemRef, opportunity_id: UUID, relation: str, skill_id: str | None = None) -> CurrentTask:
    return CurrentTask(problem_id=ref.problem_id, problem_version=ref.problem_version, opportunity_id=opportunity_id,
                       concept_id=ref.concept_id, target_skill_id=skill_id or ref.target_skill_id,
                       template_family_id=ref.template_family_id, relation=relation, difficulty=ref.difficulty)


def apply_decision(s: StudentState, p: DecisionProposal, services: Services, decision_id: UUID) -> StudentState:
    """Tác động của quyết định lên state do Member 3 quản lý: mức hỗ trợ, bài hiện tại,
    return stack, trạng thái phiên. Không đụng tới mastery."""
    update: dict = {}
    support = s.support
    if ACTION_SPECS[p.action].counts_as_assistance:
        support = support.model_copy(update={"hint_level": max(support.hint_level, p.hint_level),
                                             "support_turns_on_node": support.support_turns_on_node + 1})
    new_problem = p.action in {A.BACKTRACK, A.CHECK_TRANSFER, A.NEXT_PROBLEM}
    if new_problem:
        update.update(latest_assessment=None, latest_submission=[], observation=None, probes=[])
        support = SupportState()
        if s.current.problem_id not in s.attempted_problem_ids:
            update["attempted_problem_ids"] = s.attempted_problem_ids + [s.current.problem_id]
    if p.intent == I.PROBE_PREREQUISITE:
        # Mỗi lúc chỉ chờ một câu: câu cũ chưa được trả lời thì đóng lại là chưa xác minh.
        closed = [PrerequisiteProbe(decision_id=q.decision_id, skill_id=q.skill_id, status="unverified",
                                    answer_turn_id=s.turn_id) if q.status == "pending" else q for q in s.probes]
        update["probes"] = (closed + [PrerequisiteProbe(decision_id=decision_id,
                                                        skill_id=p.target_skill_id)])[-MAX_PROBES:]
    if p.action == A.BACKTRACK:
        frame = ReturnFrame(problem_id=s.current.problem_id, opportunity_id=s.current.opportunity_id,
                            concept_id=s.current.concept_id, skill_id=s.current.target_skill_id,
                            hint_level=s.support.hint_level)
        update["return_stack"] = s.return_stack + [frame]
        update["current"] = _task(services.problem_ref(p.problem_id), services.new_id(), "prerequisite")
    elif p.intent == I.RETURN_TO_PARENT:
        frame = s.return_stack[-1]
        update["return_stack"] = s.return_stack[:-1]
        update["current"] = _task(services.problem_ref(frame.problem_id), frame.opportunity_id, "repeat",
                                  frame.skill_id)
        support = SupportState(hint_level=frame.hint_level)
    elif new_problem:
        ref = services.problem_ref(p.problem_id)
        if p.action == A.CHECK_TRANSFER:
            relation = "cross_family"
        elif p.intent in {I.ADVANCE_CONCEPT, I.ADVANCE_DIFFICULTY}:
            relation = "initial"
        else:
            relation = "near_practice" if ref.template_family_id == s.current.template_family_id else "cross_family"
        update["current"] = _task(ref, services.new_id(), relation)
    if "current" in update and update["current"].concept_id not in s.visited_concept_ids:
        update["visited_concept_ids"] = s.visited_concept_ids + [update["current"].concept_id]
    if p.action == A.END_SESSION:
        update["status"] = "paused" if p.intent in PAUSING_INTENTS else "completed"
    update["support"] = support
    return s.model_copy(update=update)


def _next_actions(status: str) -> list[str]:
    return {"completed": [], "paused": ["resume"]}.get(status, ["submit", "request_hint", "pause"])


# --------------------------------------------------------------------------- graph

def build_graph(services: Services, config: DecisionConfig, checkpointer=None):
    def load(gs: TutorGraphState):
        turn = TurnInput.model_validate(gs["turn_input"])
        if str(turn.request_id) in gs.get("processed", {}):
            return {"duplicate": True}
        s = StudentState.model_validate(gs["student"])
        # Lời nhắn chỉ là message của lượt này; bài làm được ghi riêng ở analyze, cùng lúc chấm.
        s = s.model_copy(update={
            "turn_id": services.new_id(), "request_id": turn.request_id, "trigger": turn.trigger,
            "latest_student_message": turn.message, "status": "active", "observation": None,
            "budget": type(s.budget)()})
        return {"student": s.model_dump(mode="json"), "duplicate": False, "extraction": None}

    def extract(gs: TutorGraphState):
        """Tách bài làm (nếu bật và concept trong phạm vi). Node riêng để kết quả và chi phí lần gọi
        LLM được lưu vào checkpoint trước khi analyzer chạy."""
        s = StudentState.model_validate(gs["student"])
        turn = TurnInput.model_validate(gs["turn_input"])
        if turn.trigger != "submit":
            return {}
        outcome = _extract(s, turn.submission, services)
        if outcome is None:
            return {}
        record = outcome.record(s.turn_id).model_dump(mode="json")
        return {"extraction": record, "extraction_log": gs.get("extraction_log", []) + [record]}

    def analyze(gs: TutorGraphState):
        s = StudentState.model_validate(gs["student"])
        turn = TurnInput.model_validate(gs["turn_input"])
        update = {"probes": _answer_probe(s, turn, services)}
        if turn.trigger == "submit":
            # Analyzer và Agent nhìn cùng một bài làm: đúng các dòng này được chấm và được lưu.
            submission = turn.submission
            extraction = ExtractionRecord.model_validate(gs["extraction"]) if gs.get("extraction") else None
            if extraction is None:
                a = services.analyzer(s, submission)
            elif extraction.result.status == "extracted":
                submission = extraction.result.graded_lines()
                a = services.analyzer(s, submission)
            else:  # chưa tách được: mời viết lại, không chấm và không ghi BKT (FR04-AC2)
                a = AssessmentView(assessment_id=services.new_id(), assessment_status="needs_clarification")
            incorrect = a.assessment_status == "verified_incorrect"
            no_progress = s.support.no_progress_turns + 1 if incorrect else (
                0 if a.assessment_status == "verified_correct" else s.support.no_progress_turns)
            update.update(latest_assessment=a, latest_submission=submission,
                          support=s.support.model_copy(update={"no_progress_turns": no_progress}))
            s = s.model_copy(update=update)
            update["hypotheses"] = _track_hypotheses(s)
        status = s.latest_assessment.assessment_status if (turn.trigger == "submit" and s.latest_assessment) else None
        update["recent_turns"] = _turns(s, TurnSummary(turn_id=s.turn_id, actor="student", kind=turn.trigger,
                                                      assessment_status=status))
        return {"student": s.model_copy(update=update).model_dump(mode="json")}

    def observe(gs: TutorGraphState):
        s = StudentState.model_validate(gs["student"])
        if s.trigger != "submit" or s.latest_assessment is None:
            return {}
        result = services.observer(s, s.latest_assessment, frozenset(gs.get("observed_opportunities", [])))
        hypotheses = s.hypotheses
        if result.status.eligible and s.latest_assessment.assessment_status == "verified_correct":
            # Làm đúng độc lập: tạm coi giả thuyết lỗi của skill đó đã được kiểm tra (chờ Member 1 xác nhận).
            hypotheses = [h.model_copy(update={"status": "ruled_out"})
                          if h.skill_id == result.observed_skill_id and h.status != "ruled_out" else h
                          for h in hypotheses]
        s = s.model_copy(update={"observation": result.status, "skills": result.skills, "hypotheses": hypotheses})
        return {"student": s.model_dump(mode="json"),
                "observed_opportunities": sorted(result.observed_opportunities)}

    def readiness(gs: TutorGraphState):
        s = StudentState.model_validate(gs["student"])
        ready = compute_readiness(project_state(s, config))
        return {"student": s.model_copy(update={"readiness": ready}).model_dump(mode="json")}

    def context(gs: TutorGraphState):
        s = StudentState.model_validate(gs["student"])
        try:
            ctx = services.tools(s, config)
        except Exception as error:  # KG/RAG lỗi: chạy tiếp không có tool, policy dùng luật/template
            ctx = TurnContext(kg_enabled=False, rag_enabled=False, tool_errors=[type(error).__name__])
        return {"context": ctx.model_dump(mode="json")}

    def decide(gs: TutorGraphState):
        s = project_state(StudentState.model_validate(gs["student"]), config)
        ctx = TurnContext.model_validate(gs["context"])
        record = run_decision(s, ctx, services.proposer, config, decision_id=services.new_id(),
                              created_at=services.clock(), workflow_version=WORKFLOW_VERSION)
        return {"decision": record.model_dump(mode="json")}

    def generate(gs: TutorGraphState):
        s = StudentState.model_validate(gs["student"])
        final = PedagogicalDecision.model_validate(gs["decision"]).final
        message, source = services.generator(s, final, TurnContext.model_validate(gs["context"]))
        return {"message": message, "response_source": source}

    def verify(gs: TutorGraphState):
        s = StudentState.model_validate(gs["student"])
        record = PedagogicalDecision.model_validate(gs["decision"])
        message, source = gs["message"], gs["response_source"]
        if services.verifier(s, record.final, message):
            message, source = services.generator.safe(record.final), "template_fallback"
            record = record.model_copy(update={"regenerations_used": 1})
            if services.verifier(s, record.final, message):
                message, source = "Mình cần kiểm tra lại câu trả lời này. Em đợi một chút rồi gửi lại nhé.", "system"
        return {"message": message, "response_source": source, "decision": record.model_dump(mode="json")}

    def commit(gs: TutorGraphState):
        s = StudentState.model_validate(gs["student"])
        record = PedagogicalDecision.model_validate(gs["decision"])
        final = record.final
        s = apply_decision(s, final, services, record.decision_id)
        s = s.model_copy(update={
            "state_version": s.state_version + 1,
            "recent_turns": _turns(s, TurnSummary(turn_id=record.decision_id, actor="tutor", kind="decision",
                                                  action=final.action, hint_level=final.hint_level))})
        reply = TutorReply(session_id=s.session_id, state_version=s.state_version, decision_id=record.decision_id,
                           action=final.action, intent=final.intent, hint_level=final.hint_level,
                           message=gs["message"], response_source=gs["response_source"],
                           problem_id=s.current.problem_id, problem_prompt=services.problem_prompt(s.current.problem_id),
                           status=s.status, next_actions=_next_actions(s.status))
        reply_json = reply.model_dump(mode="json")
        return {"student": s.model_dump(mode="json"), "reply": reply_json,
                "processed": {**gs.get("processed", {}), gs["turn_input"]["request_id"]: reply_json},
                "decision_log": gs.get("decision_log", []) + [gs["decision"]]}

    graph = StateGraph(TutorGraphState)
    nodes = [("load", load), ("extract", extract), ("analyze", analyze), ("observe", observe),
             ("readiness", readiness), ("context", context), ("decide", decide), ("generate", generate),
             ("verify", verify), ("commit", commit)]
    for name, fn in nodes:
        graph.add_node(name, fn)
    graph.add_edge(START, "load")
    graph.add_conditional_edges("load", lambda gs: END if gs.get("duplicate") else "extract", ["extract", END])
    for (left, _), (right, _) in zip(nodes[1:], nodes[2:]):
        graph.add_edge(left, right)
    graph.add_edge("commit", END)
    return graph.compile(checkpointer=checkpointer)


# --------------------------------------------------------------------------- khóa theo phiên

class SessionLocks(Protocol):
    """Khóa loại trừ theo phiên (FR-11: mỗi lượt xử lý đúng một lần).

    Mọi engine truy cập cùng một phiên phải dùng chung một ``SessionLocks``. Nhiều tiến trình
    (nhiều worker API) cần bản dùng chung giữa các tiến trình, ví dụ advisory lock PostgreSQL
    khi nối checkpointer DB; bản trong tiến trình dưới đây chỉ bảo vệ các engine cùng tiến trình."""

    def hold(self, session_id: str) -> AbstractContextManager: ...


class InProcessSessionLocks:
    """Một ``threading.Lock`` cho mỗi phiên, dùng chung giữa các engine trong cùng tiến trình."""

    def __init__(self):
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def hold(self, session_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(session_id, threading.Lock())


# Mặc định mọi TutorEngine trong tiến trình dùng chung bộ khóa này.
PROCESS_SESSION_LOCKS = InProcessSessionLocks()


# --------------------------------------------------------------------------- engine

class TutorEngine:
    """Điểm vào cho API (Member 1): mở phiên, xử lý một lượt, đọc state và decision log."""

    def __init__(self, config: DecisionConfig, services: Services | None = None, checkpointer=None,
                 locks: SessionLocks = PROCESS_SESSION_LOCKS):
        self.config = config
        self.services = services or Services()
        self.graph = build_graph(self.services, config, checkpointer or InMemorySaver())
        self.locks = locks

    @staticmethod
    def _cfg(session_id) -> dict:
        return {"configurable": {"thread_id": str(session_id)}, "recursion_limit": 25}

    def _values(self, session_id) -> dict:
        values = self.graph.get_state(self._cfg(session_id)).values
        if not values:
            raise KeyError(f"unknown session {session_id}")
        return values

    def start(self, student_id: str, problem_id: str, *, session_id: UUID | None = None) -> TutorReply:
        sv = self.services
        ref = sv.problem_ref(problem_id)
        sid = session_id or sv.new_id()
        state = StudentState(student_id=student_id, session_id=sid, state_version=1, turn_id=sv.new_id(),
                             request_id=sv.new_id(), status="active", trigger="resume",
                             current=_task(ref, sv.new_id(), "initial"), visited_concept_ids=[ref.concept_id],
                             readiness=Readiness(ready_to_advance=False, criteria_version=READINESS_VERSION,
                                                 unmet=["too_few_observations"]))
        prompt = sv.problem_prompt(problem_id)
        reply = TutorReply(session_id=sid, state_version=1, message=f"Chào em! Mình cùng làm bài này nhé: {prompt}",
                           response_source="template", problem_id=problem_id, problem_prompt=prompt,
                           status="active", next_actions=_next_actions("active"))
        with self.locks.hold(str(sid)):
            if self.graph.get_state(self._cfg(sid)).values:
                raise ValueError(f"session {sid} already exists")
            self.graph.update_state(self._cfg(sid), {
                "student": state.model_dump(mode="json"), "observed_opportunities": [], "decision_log": [],
                "extraction_log": [],
                "reply": reply.model_dump(mode="json"), "processed": {}, "duplicate": False}, as_node="commit")
        return reply

    def turn(self, session_id: UUID, turn: TurnInput) -> TutorReply:
        """Xử lý một lượt, đúng một lần cho mỗi ``request_id``.

        Đọc checkpoint, kiểm tra request và chạy graph nằm trong cùng một khóa của phiên, nên hai
        request gửi đồng thời (kể cả cùng ``request_id``) được xử lý lần lượt:
        - Request đã hoàn tất: trả lại phản hồi đã lưu, không chạy graph.
        - Lượt trước lỗi giữa chừng (checkpoint còn node chờ chạy): cùng request thì chạy tiếp từ
          node lỗi, không phân tích lại; request khác thì từ chối bằng ``TurnInProgress``.
        """
        cfg = self._cfg(session_id)
        with self.locks.hold(str(session_id)):
            snapshot = self.graph.get_state(cfg)
            if not snapshot.values:
                raise KeyError(f"unknown session {session_id}")
            request_id = str(turn.request_id)
            done = snapshot.values.get("processed", {})
            if request_id in done:
                return TutorReply.model_validate(done[request_id]).model_copy(update={"duplicate": True})
            if snapshot.next:
                pending = snapshot.values["turn_input"]["request_id"]
                if pending != request_id:
                    raise TurnInProgress(pending)
                out = self.graph.invoke(None, cfg)
            else:
                if snapshot.values["student"]["status"] == "completed":
                    raise SessionClosed(f"session {session_id} is completed")
                out = self.graph.invoke({"turn_input": turn.model_dump(mode="json")}, cfg)
            return TutorReply.model_validate(out["processed"][request_id])

    def state(self, session_id: UUID) -> StudentState:
        return StudentState.model_validate(self._values(session_id)["student"])

    def decisions(self, session_id: UUID) -> list[PedagogicalDecision]:
        return [PedagogicalDecision.model_validate(d) for d in self._values(session_id).get("decision_log", [])]

    def extractions(self, session_id: UUID) -> list[ExtractionRecord]:
        return [ExtractionRecord.model_validate(r) for r in self._values(session_id).get("extraction_log", [])]
