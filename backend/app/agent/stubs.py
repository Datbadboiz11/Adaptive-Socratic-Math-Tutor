"""Stub cho các phần chưa có để khung LangGraph chạy được từ đầu đến cuối.

KHÔNG phải triển khai thật:
- StubAnalyzer thay validator/analyzer của Member 1 (chỉ so khớp chuỗi trên vài bài mẫu).
- stub_observe thay observation builder + BKT của Member 1 (tham số mặc định, không fit).
- StubTools thay RAG (Member 2) và problem bank. KG là bản thật (``kg_tool.KGTool``): đọc registry,
  dùng cả cạnh nháp vì registry chưa có cạnh nào được duyệt.
- TemplateGenerator/AnswerLeakVerifier là bản tối thiểu của bước sinh/kiểm tra phản hồi.
- unverified_probe thay bước xác minh câu trả lời cho câu hỏi kiểm tra prerequisite (chờ LLM
  extraction): luôn trả "unverified", nên hiện chưa câu trả lời nào được tính là bằng chứng.
Mọi stub có cùng chữ ký với bản thật dự kiến nên có thể thay từng phần. Đồ giả chỉ dùng cho
test (Agent giả, LLM giả) nằm riêng ở ``fakes.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from uuid import uuid4

from app.agent.decision import (
    AssessmentView, DecisionConfig, DecisionIntent, DecisionProposal, ExperimentConfiguration,
    ObservationStatus, SkillState, StudentState,
)
from app.agent.kg_tool import KGTool
from app.agent.tools import ProblemRef, RetrievedContent, TurnContext

I = DecisionIntent


# --------------------------------------------------------------------------- ngân hàng bài mẫu

@dataclass(frozen=True)
class DemoError:
    pattern: str
    error_family: str
    skill_id: str
    misconception_id: str | None = None


@dataclass(frozen=True)
class DemoProblem:
    ref: ProblemRef
    prompt: str
    answer_forms: tuple[str, ...]
    errors: tuple[DemoError, ...] = ()


def _ref(pid, concept, skill, family, difficulty=1):
    return ProblemRef(problem_id=pid, problem_version="0.1.0", concept_id=concept, target_skill_id=skill,
                      template_family_id=family, difficulty=difficulty)


DIST = "SK-A02-DISTRIBUTE"
SOLVE = "SK-E02-SOLVE"
SIGNED = "SK-N01-SIGNED-ADD"

DEMO_PROBLEMS = {p.ref.problem_id: p for p in [
    DemoProblem(_ref("E02-P001", "E02", SOLVE, "linear_with_distribution"), "Giải phương trình 2(x - 3) = 10.",
                ("x=8",), (DemoError("2x-3", "distribution_error", DIST, "M_DIST_01"),)),
    DemoProblem(_ref("E02-P002", "E02", SOLVE, "linear_with_distribution"), "Giải phương trình 3(x + 1) = 12.",
                ("x=3",), (DemoError("3x+1", "distribution_error", DIST, "M_DIST_01"),)),
    DemoProblem(_ref("E02-P003", "E02", SOLVE, "linear_both_sides", 2), "Giải phương trình 5x - 7 = 2x + 8.",
                ("x=5",), (DemoError("7x", "sign_error", SOLVE, "M_MOVE_SIGN"),)),
    DemoProblem(_ref("A02-P001", "A02", DIST, "distribute_negative"), "Khai triển -2(3y + 4).",
                ("-6y-8",), (DemoError("-6y+4", "distribution_error", DIST, "M_DIST_01"),
                             DemoError("-6y+8", "sign_error", DIST, "M_NEG_DIST"))),
    DemoProblem(_ref("A02-P002", "A02", DIST, "distribute_basic"), "Khai triển 4(a - 5).",
                ("4a-20",), (DemoError("4a-5", "distribution_error", DIST, "M_DIST_01"),)),
    DemoProblem(_ref("N01-P001", "N01", SIGNED, "signed_add_basic"), "Tính (-7) + 3.",
                ("-4",), (DemoError("-10", "sign_error", SIGNED, None),)),
    DemoProblem(_ref("E03-P001", "E03", "SK-E03-PRIMARY", "word_to_linear", 2),
                "Tổng của một số và 5 bằng 12. Lập phương trình và tìm số đó.", ("x=7",)),
]}

DEMO_CONTENT = [
    RetrievedContent(content_id="KB-A02-QUESTION-01", skill_id=DIST, content_type="question", disclosure_level=0,
                     text="Nếu viết k(a - b) thành (a - b) + (a - b) + ... (k lần), em thấy số b xuất hiện mấy lần?"),
    RetrievedContent(content_id="KB-A02-HINT-01", skill_id=DIST, content_type="hint", disclosure_level=1,
                     text="Khi nhân một số với một tổng hoặc hiệu trong ngoặc, em cần nhân số đó với từng số hạng trong ngoặc."),
    RetrievedContent(content_id="KB-A02-EXAMPLE-01", skill_id=DIST, content_type="example", disclosure_level=3,
                     text="Ví dụ: 3(a + 2) = 3·a + 3·2 = 3a + 6. Số 3 được nhân với cả a và 2."),
    RetrievedContent(content_id="KB-A02-EXPLAIN-01", skill_id=DIST, content_type="explanation", disclosure_level=4,
                     text="Tính chất phân phối: k(a + b) = ka + kb và k(a - b) = ka - kb. "
                          "Ví dụ 5(y - 1) = 5y - 5: cả hai số hạng trong ngoặc đều được nhân với 5."),
    RetrievedContent(content_id="KB-E02-HINT-01", skill_id=SOLVE, content_type="hint", disclosure_level=1,
                     text="Khi giải phương trình, em làm cùng một phép toán ở cả hai vế."),
    RetrievedContent(content_id="KB-E02-EXAMPLE-01", skill_id=SOLVE, content_type="example", disclosure_level=3,
                     text="Ví dụ: 4x + 1 = 9 → trừ 1 ở hai vế: 4x = 8 → chia hai vế cho 4: x = 2."),
    RetrievedContent(content_id="KB-N01-HINT-01", skill_id=SIGNED, content_type="hint", disclosure_level=1,
                     text="Cộng hai số khác dấu: lấy hiệu hai giá trị tuyệt đối, dấu theo số có giá trị tuyệt đối lớn hơn."),
]


def problem_ref(problem_id: str) -> ProblemRef:
    return DEMO_PROBLEMS[problem_id].ref


def problem_prompt(problem_id: str) -> str | None:
    problem = DEMO_PROBLEMS.get(problem_id)
    return problem.prompt if problem else None


# --------------------------------------------------------------------------- analyzer (Member 1)

_ALLOWED = re.compile(r"^[0-9a-z+\-*/().=·^]+$")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower()).replace("−", "-").replace(",", ".")


class StubAnalyzer:
    def __call__(self, state: StudentState, steps: list[str]) -> AssessmentView:
        problem = DEMO_PROBLEMS[state.current.problem_id]
        lines = [normalize(line) for line in steps if line.strip()]

        def view(status, **kw):
            return AssessmentView(assessment_id=uuid4(), assessment_status=status, **kw)

        if not lines or not all(_ALLOWED.match(line) for line in lines):
            return view("needs_clarification")
        for number, line in enumerate(lines, start=1):
            for err in problem.errors:
                if err.pattern in line:
                    return view("verified_incorrect", first_error_step=number, primary_skill_id=err.skill_id,
                                error_family=err.error_family, misconception_candidate=err.misconception_id,
                                diagnosis_status="suspected" if err.misconception_id else "unknown")
        if lines[-1] in problem.answer_forms:
            return view("verified_correct", primary_skill_id=problem.ref.target_skill_id)
        return view("verified_incorrect", primary_skill_id=problem.ref.target_skill_id,
                    final_answer_only=len(lines) == 1)


# --------------------------------------------------------------------------- observation + BKT (Member 1)

BKT_VERSION = "stub-bkt-0.1.0"
BKT_PARAMS = {"L0": 0.3, "T": 0.1, "G": 0.2, "S": 0.1}


@dataclass(frozen=True)
class ObservationResult:
    status: ObservationStatus
    skills: list[SkillState]
    observed_opportunities: frozenset[str]
    observed_skill_id: str | None = None


def bkt_update(p: float, correct: bool, params=BKT_PARAMS) -> float:
    g, s, t = params["G"], params["S"], params["T"]
    if correct:
        posterior = p * (1 - s) / (p * (1 - s) + (1 - p) * g)
    else:
        posterior = p * s / (p * s + (1 - p) * (1 - g))
    return posterior + (1 - posterior) * t


def stub_observe(state: StudentState, a: AssessmentView, observed: frozenset[str]) -> ObservationResult:
    skills = {s.skill_id: s for s in state.skills}
    correct = a.assessment_status == "verified_correct"
    if a.assessment_status not in {"verified_correct", "verified_incorrect"}:
        return ObservationResult(ObservationStatus(eligible=False, reason="not_gradable"), list(skills.values()), observed)
    skill_id = state.current.target_skill_id if correct else (a.primary_skill_id or state.current.target_skill_id)
    skill = skills.get(skill_id) or SkillState(skill_id=skill_id, independent_observations=0,
                                               parameter_version=BKT_VERSION)
    opportunity = str(state.current.opportunity_id)
    assisted = state.support.hint_level > 0 or state.support.support_turns_on_node > 0
    if opportunity in observed or assisted:
        if correct:
            skills[skill_id] = skill.model_copy(update={"assisted_correct": skill.assisted_correct + 1})
        reason = "already_observed" if opportunity in observed else "assisted_attempt"
        return ObservationResult(ObservationStatus(eligible=False, reason=reason), list(skills.values()), observed)
    p = skill.p_mastery if skill.p_mastery is not None else BKT_PARAMS["L0"]
    skills[skill_id] = skill.model_copy(update={
        "p_mastery": round(bkt_update(p, correct), 6),
        "independent_observations": skill.independent_observations + 1,
        "recent_independent": (skill.recent_independent + [correct])[-5:],
        "parameter_version": BKT_VERSION})
    status = ObservationStatus(eligible=True, reason="first_independent_attempt", observation_id=uuid4())
    return ObservationResult(status, list(skills.values()), observed | {opportunity}, skill_id)


def unverified_probe(state: StudentState, probe, message: str) -> str:
    """Chưa có bộ xác minh câu trả lời tự do: không kết luận gì từ câu trả lời của học sinh."""
    return "unverified"


# --------------------------------------------------------------------------- tools: KG, RAG, problem bank

@dataclass
class StubTools:
    """KG thật + RAG và problem bank giả. ``kg`` mặc định đọc registry và dùng cả cạnh nháp
    (chế độ dev); truyền ``KGTool(neo4j=...)`` để truy vấn qua Neo4j."""

    kg: KGTool = field(default_factory=lambda: KGTool(include_drafts=True))
    content: list[RetrievedContent] = field(default_factory=lambda: list(DEMO_CONTENT))
    problems: dict[str, DemoProblem] = field(default_factory=lambda: dict(DEMO_PROBLEMS))

    def __call__(self, state: StudentState, config: DecisionConfig) -> TurnContext:
        kg = config.configuration != ExperimentConfiguration.NO_KG
        rag = config.configuration != ExperimentConfiguration.NO_RAG
        calls, retrieved = 0, []
        concept = state.current.concept_id
        found = None
        if kg:
            calls += 1
            found = self.kg(concept)
        edges = found.edges if found else []
        if rag:
            calls += 1
            skills = {state.current.target_skill_id}
            if state.latest_assessment and state.latest_assessment.primary_skill_id:
                skills.add(state.latest_assessment.primary_skill_id)
            skills |= {sk for e in edges if e.depth == 1 for sk in e.source_skill_ids}
            retrieved = [c for c in self.content if c.skill_id in skills][:10]
        calls += 1
        problems = [p.ref for p in self.problems.values()][:20]
        current = self.problems.get(state.current.problem_id)
        return TurnContext(current_problem_prompt=current.prompt if current else None,
                           retrieved=retrieved, edges=edges, problems=problems, tool_calls_used=calls,
                           next_concepts=found.next_concepts if found else [],
                           kg_source=found.source if found else None,
                           graph_version=found.graph_version if found else None,
                           tool_errors=found.errors if found else [], kg_enabled=kg, rag_enabled=rag)


# --------------------------------------------------------------------------- generator + verifier

TEMPLATES = {
    I.RESOLVE_INPUT: "Mình chưa đọc được bài làm này. Em viết mỗi bước trên một dòng, ví dụ: 2x + 1 = 7 nhé.",
    I.RESTATE_TASK: "Mình cùng đọc lại đề nhé: {prompt} Đề bài đang yêu cầu em tìm gì?",
    I.ELICIT_REASONING: "Em giải thích giúp mình vì sao em viết được bước{step} như vậy không?",
    I.DISTINGUISH_HYPOTHESIS: "Ở bước{step}, em đã biến đổi phần nào của biểu thức? "
                              "Em kiểm tra xem phép biến đổi đó đã áp dụng cho đủ các phần chưa nhé.",
    I.PROBE_PREREQUISITE: "Trước khi làm tiếp, em thử trả lời câu này nhé: {content}",
    I.PROMPT_SELF_CHECK: "Em thử thay kết quả vào đề bài để tự kiểm tra lại nhé.",
    I.LOCATE_ERROR: "Bài làm có chỗ cần xem lại ở bước{step}. {content}",
    I.RECALL_RULE: "{content}",
    I.TARGET_MISCONCEPTION: "{content}",
    I.DECOMPOSE_STEP: "Mình chia nhỏ bước này nhé. {content} Giờ em làm lại riêng bước{step} thôi.",
    I.ANALOGOUS_EXAMPLE: "Mình xem một ví dụ khác trước nhé. {content} Giờ em thử áp dụng vào bài của mình.",
    I.EXPLAIN_CONCEPT: "{content} Em thử làm lại bài của mình theo cách này nhé.",
    I.REVIEW_PREREQUISITE: "Mình cùng ôn một kiến thức nền trước, xong sẽ quay lại bài cũ. Bài ôn: {new_prompt}",
    I.INDEPENDENT_CHECK: "Em sửa được rồi! Giờ em tự làm bài mới này nhé, không có gợi ý: {new_prompt}",
    I.CONTINUE_PRACTICE: "Đúng rồi! Em làm tiếp bài này nhé: {new_prompt}",
    I.ADVANCE_DIFFICULTY: "Em làm tốt rồi. Mình thử một bài khó hơn nhé: {new_prompt}",
    I.ADVANCE_CONCEPT: "Em đã sẵn sàng cho phần tiếp theo. Bài mới: {new_prompt}",
    I.RETURN_TO_PARENT: "Tốt lắm! Giờ mình quay lại bài lúc nãy nhé: {new_prompt}",
    I.SWITCH_PROBLEM: "Mình đổi sang một bài khác để thử cách tiếp cận mới nhé: {new_prompt}",
    I.STUDENT_REQUEST: "Mình tạm dừng ở đây nhé. Lần sau em có thể tiếp tục từ bài đang làm.",
    I.SESSION_GOAL_MET: "Em đã hoàn thành mục tiêu của buổi học hôm nay. Hẹn gặp lại!",
    I.BUDGET_EXHAUSTED: "Buổi học hôm nay đến đây là hết thời lượng. Em có thể tiếp tục vào lần sau.",
    I.STUCK_LIMIT: "Mình đã thử nhiều cách cho bước này rồi. Em nghỉ một chút rồi quay lại sau nhé.",
    I.CONTENT_EXHAUSTED: "Em đã làm hết bài luyện của phần này trong buổi hôm nay. Mình tạm dừng, lần sau học tiếp nhé.",
    I.SYSTEM_FALLBACK: "Hệ thống đang trục trặc nên mình tạm dừng lượt này. Bài làm của em đã được lưu.",
}
GENERIC_CONTENT = {
    I.RECALL_RULE: "Em nhớ lại quy tắc của dạng bài này rồi áp dụng vào bước đang làm nhé.",
    I.TARGET_MISCONCEPTION: "Em thử giải thích lại quy tắc em đã dùng ở bước này bằng lời của mình nhé.",
    I.PROBE_PREREQUISITE: "em nhắc lại quy tắc nền của dạng bài này giúp mình nhé.",
}


@dataclass
class TemplateGenerator:
    """Sinh câu từ template + nội dung đã truy xuất. Không nhận đáp án/lời giải của bài."""

    prompts: dict[str, str] = field(default_factory=lambda: {k: v.prompt for k, v in DEMO_PROBLEMS.items()})

    def __call__(self, state: StudentState, p: DecisionProposal, ctx: TurnContext) -> tuple[str, str]:
        content = " ".join(c.text for cid in p.content_ids if (c := ctx.content(cid)))
        a = state.latest_assessment
        values = {
            "content": content or GENERIC_CONTENT.get(p.intent, ""),
            "step": f" {a.first_error_step}" if a and a.first_error_step else " vừa rồi",
            "prompt": self.prompts.get(state.current.problem_id, ""),
            "new_prompt": self.prompts.get(p.problem_id or "", ""),
        }
        return " ".join(TEMPLATES[p.intent].format(**values).split()), "template"

    def safe(self, p: DecisionProposal) -> str:
        """Bản dự phòng không chèn nội dung truy xuất hay đề bài."""
        return " ".join(TEMPLATES[p.intent].format(content=GENERIC_CONTENT.get(p.intent, ""), step=" vừa rồi",
                                                   prompt="", new_prompt="").split())


class AnswerLeakVerifier:
    """Chặn phản hồi chứa đáp án cuối của bài đang làm hoặc bài vừa giao. Chỉ khớp chuỗi;
    chưa kiểm tra tính đúng toán của câu chữ."""

    def __call__(self, state: StudentState, p: DecisionProposal, message: str) -> list[str]:
        text = normalize(message)
        problems = {state.current.problem_id, p.problem_id} - {None}
        leaks = [form for pid in problems if pid in DEMO_PROBLEMS for form in DEMO_PROBLEMS[pid].answer_forms
                 if form in text]
        return [f"answer_leak:{form}" for form in leaks]
