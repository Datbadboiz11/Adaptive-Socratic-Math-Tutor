"""Soạn lịch sử cho bộ tình huống thích ứng bằng code, thay cho viết JSON tay (plan §11.5).

``Session`` ghi từng sự kiện rồi đẩy nó qua đúng các bước ghi state mà replay dùng
(``replay._student_turn`` / ``_tutor_turn``, tức các hàm của graph). Nhờ vậy ``task`` của mỗi sự kiện
luôn là bài hệ thống đang giữ, quyết định giao bài sai luật gate bị từ chối ngay lúc soạn, và người
soạn xem được state (mastery, số observation) ở bất kỳ lúc nào. Người soạn chỉ cung cấp những gì hệ
thống nhận từ bên ngoài: lượt của học sinh, assessment và quyết định của tutor.

Với bài thật, ``Session(analyzer=...)`` và ``work(...)`` lấy assessment từ chính validator của hệ
thống thay cho người soạn, và ``tools`` lấy context bằng công cụ của hệ thống (``ApprovedTools``).

Mọi ID là UUID5 từ mã tình huống và số thứ tự, nên chạy lại cho đúng file cũ.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid5

from app.agent.decision import ACTION_SPECS, DecisionConfig, DecisionIntent, StudentState
from app.agent.graph import Services, task_for
from app.agent.kg_tool import KGTool
from app.agent.observation import ObservationLedger
from app.agent.stubs import retrieval_skills
from app.agent.tools import RetrievedContent, TurnContext
from research.scenarios.contracts import (
    BKTParameters, HistoryEvent, ProblemSource, ScenarioDraft, StrategyLabels,
)
from research.scenarios.replay import _initial_state, _student_turn, _tutor_turn

MAX_CONTEXT_CONTENT = 10
MAX_CONTEXT_PROBLEMS = 20


class Session:
    """Một phiên của một học sinh, soạn theo thứ tự xảy ra. Kết thúc bằng ``scenario(...)``."""

    def __init__(self, scenario_id: str, first_problem: str, *, problems: list[ProblemSource],
                 parameters: dict[str, BKTParameters], content: list[RetrievedContent], kg: KGTool,
                 source_reference: str, analyzer: Callable[..., object] | None = None,
                 tools: Callable[[StudentState, DecisionConfig], TurnContext] | None = None):
        self.id = scenario_id
        self.sources = {p.problem.problem_id: p for p in problems}
        self.refs = {pid: p.problem for pid, p in self.sources.items()}
        self.parameters, self.content, self.kg, self.source_reference = parameters, content, kg, source_reference
        self.no_evidence = frozenset(pid for pid, p in self.sources.items() if not p.target_evidence)
        # ``analyzer(state, lines)`` trả AssessmentView, như ``Services.analyzer``; ``tools`` trả context
        # như ``Services.tools``. None: người soạn tự cung cấp assessment, context lấy từ ``content``.
        self.analyzer, self.tools = analyzer, tools
        self.events: list[HistoryEvent] = []
        self._count = 0
        self._ledger = ObservationLedger()
        self._services = Services(problem_ref=self.refs.__getitem__)
        self._first_task = task_for(self.refs[first_problem], self._uuid("opportunity"), "initial")
        self.state: StudentState | None = None

    def _uuid(self, kind: str) -> UUID:
        self._count += 1
        return uuid5(NAMESPACE_URL, f"adaptive-scenario:{self.id}:{kind}:{self._count}")

    @property
    def _dataset(self):
        return SimpleNamespace(parameters=self.parameters)

    def _task(self):
        return self.state.current if self.state else self._first_task

    # ------------------------------------------------------------------ lượt của học sinh

    def _student(self, kind: str, **fields) -> "Session":
        event = HistoryEvent(turn_id=self._uuid("turn"), request_id=self._uuid("request"), task=self._task(),
                             actor="student", kind=kind, **fields)
        if self.state is None:
            draft = SimpleNamespace(scenario_id=self.id, student_id=f"{self.id}-student",
                                    session_id=uuid5(NAMESPACE_URL, f"adaptive-scenario:{self.id}:session"))
            self.state = _initial_state(draft, self._dataset, event, self.refs)
        elif self.events[-1].actor == "student":
            raise ValueError(f"{self.id}: the tutor must answer before the next student turn")
        self.state, self._ledger = _student_turn(self.state, event, self._services, self._ledger,
                                                   self.parameters, [], f"{self.id} event {len(self.events) + 1}",
                                                   self.no_evidence)
        self.events.append(event)
        return self

    def submit(self, lines: list[str], status: str, *, step: int | None = None, skill: str | None = None,
               family: str | None = None, misconception: str | None = None, final_only: bool = False) -> "Session":
        """Nộp bài kèm assessment do người soạn cung cấp. ``skill`` mặc định là skill đích của bài."""
        assessment = {
            "assessment_id": self._uuid("assessment"), "assessment_status": status, "first_error_step": step,
            "primary_skill_id": skill or (self._task().target_skill_id if status.startswith("verified") else None),
            "error_family": family, "misconception_candidate": misconception,
            "diagnosis_status": "suspected" if misconception else "unknown", "final_answer_only": final_only}
        return self._student("submit", submission=lines, assessment=assessment)

    def work(self, lines: list[str], expect: str) -> "Session":
        """Nộp bài và để validator của hệ thống chấm. ``expect`` là kết quả người soạn muốn có
        (``verified_correct``, ``verified_incorrect``, ``unfinished``, ``needs_clarification``...); chấm
        ra khác thì báo lỗi ngay, để nhãn không dựa trên một lần chấm mà hệ thống không đưa ra."""
        if self.analyzer is None:
            raise ValueError(f"{self.id}: work() needs a Session analyzer")
        view = self.analyzer(SimpleNamespace(current=self._task()), lines)
        got = "unfinished" if view.unfinished else view.assessment_status
        if got != expect:
            raise ValueError(f"{self.id}: validator graded {lines} on {self._task().problem_id} as {got}, "
                             f"not {expect}")
        assessment = view.model_copy(update={"assessment_id": self._uuid("assessment")})
        return self._student("submit", submission=lines, assessment=assessment)

    def correct(self, lines: list[str], *, final_only: bool = False) -> "Session":
        return self.submit(lines, "verified_correct", final_only=final_only)

    def hint(self, message: str | None = None) -> "Session":
        return self._student("request_hint", message=message)

    def message(self, text: str) -> "Session":
        return self._student("message", message=text)

    def pause(self, message: str | None = None) -> "Session":
        return self._student("pause", message=message)

    def resume(self) -> "Session":
        return self._student("resume")

    # ------------------------------------------------------------------ quyết định của tutor

    def tutor(self, action: str, intent: str, level: int = 0, *, problem: str | None = None,
              skill: str | None = None) -> "Session":
        """Quyết định hệ thống đã đưa ra ở lượt này. ``problem`` khi giao bài; ``skill`` khi hỏi kiểm tra
        prerequisite (giao bài thì lấy skill của bài)."""
        if self.state is None or self.events[-1].actor != "student":
            raise ValueError(f"{self.id}: a tutor decision answers a student turn")
        if problem and not skill:
            skill = self.refs[problem].target_skill_id
        if intent == DecisionIntent.RETURN_TO_PARENT.value and problem is None:
            problem = self.state.return_stack[-1].problem_id
            skill = self.state.return_stack[-1].skill_id
        if ACTION_SPECS[action].requires_problem and problem is None:
            raise ValueError(f"{self.id}: {action} needs a problem")
        event = HistoryEvent(turn_id=self._uuid("turn"), request_id=self._uuid("request"), task=self._task(),
                             actor="tutor", kind="decision", action=action, intent=intent, hint_level=level,
                             problem_id=problem, target_skill_id=skill)
        upcoming = SimpleNamespace(task=SimpleNamespace(opportunity_id=self._uuid("opportunity")))
        self.state, self._ledger = _tutor_turn(self.state, self._ledger, event, upcoming, self._services,
                                               self.refs, self.kg, f"{self.id} event {len(self.events) + 1}")
        self.events.append(event)
        return self

    # ------------------------------------------------------------------ tình huống

    def scenario(self, title: str, tags: list[str], labels: StrategyLabels, *, split: str | None = "dev",
                 source: str = "synthetic_authoring") -> ScenarioDraft:
        """Tình huống kết thúc ở lượt học sinh vừa ghi. Context lấy như tool của hệ thống: nội dung của
        skill đang học, skill của lỗi vừa chấm và prerequisite trực tiếp; cạnh KG để ``build`` điền."""
        if self.state is None or self.events[-1].actor != "student":
            raise ValueError(f"{self.id}: a scenario ends at a student turn")
        prompt = self.sources[self.state.current.problem_id].prompt
        if self.tools is not None:
            found = self.tools(self.state, DecisionConfig(configuration="full", policy_version="scenario-authoring"))
            context = TurnContext(current_problem_prompt=prompt, retrieved=found.retrieved,
                                  problems=found.problems[:MAX_CONTEXT_PROBLEMS])
        else:
            edges = self.kg(self.state.current.concept_id).edges
            skills = retrieval_skills(self.state, edges)
            retrieved = [c for c in self.content if c.skill_id in skills][:MAX_CONTEXT_CONTENT]
            context = TurnContext(current_problem_prompt=prompt, retrieved=retrieved,
                                  problems=list(self.refs.values())[:MAX_CONTEXT_PROBLEMS])
        return ScenarioDraft(
            scenario_id=self.id, title=title, student_id=self.state.student_id, session_id=self.state.session_id,
            history_group_id=f"{self.id}-history", source=source, source_reference=self.source_reference,
            split=split, tags=tags, history=self.events, context=context, labels=labels)
