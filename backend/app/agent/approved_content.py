"""Nội dung đã duyệt cho Agent: thay bài mẫu và RAG giả của ``stubs`` bằng dữ liệu thật của Member 2.

- **Problem bank:** 78 bài của 13 pack M2-ORIG02 đã được người dùng duyệt (``member2_runtime.demo_catalog``,
  đã kiểm checksum và trạng thái duyệt). Chấm bằng chế độ đáp án cuối của validator
  (``assessment_mode``), đúng như web của Member 2.
- **RAG:** 91 chunk KB (13 giải thích, 39 hint, 39 ví dụ có lời giải) chiếu từ chính các pack đó bằng
  ``kb_projection.project``, là cùng dữ liệu Member 2 nạp vào PostgreSQL. Ở đây lọc trong bộ nhớ, không
  cần cơ sở dữ liệu và không dùng embedding: lấy theo skill rồi theo mức tiết lộ. Khi chạy với DB thì
  thay bằng ``kb_tool.bind_runtime_tool``.
- **Luật chống lộ đáp án của KB** được giữ: không lấy ví dụ cùng họ mẫu, cùng source group hoặc cùng
  dòng dõi (lineage) với bài đang làm; RAG không bao giờ trả đáp án bài đang làm.

Mức tiết lộ (``disclosure_level``) theo quy ước của Agent: hint giữ mức 1–3 của KB, ví dụ mức 3. Giải
thích khái niệm của KB có mức 0 trong KB nhưng được xếp mức 4 cho Agent, vì hành động giải thích của
Agent là mức tiết lộ cao nhất (``stubs.DEMO_CONTENT`` dùng cùng quy ước).

Concept Member 3 chưa được duyệt nên không có ở đây; ``include`` cho phép thêm pack khác khi đã duyệt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import re

from app.agent.decision import MAX_HINT_LEVEL, DecisionConfig, ExperimentConfiguration, StudentState
from app.agent.kg_tool import KGTool
from app.agent.stubs import retrieval_skills
from app.agent.tools import ProblemRef, RetrievedContent, TurnContext
from app.generation.verifier import AnswerKey

DIFFICULTY = {"introductory": 1, "standard": 2}
CONTENT_TYPE = {"explanation": "explanation", "hint": "hint", "example": "example"}
MAX_RETRIEVED = 10
MAX_PROBLEMS = 20


def answer_forms(reference_answer: str) -> tuple[str, ...]:
    """Tách đáp án nhiều phần (``25;{1/2,3}``, ``(3,-20)``, ``[-7,+inf)``, ``45/126 < 49/126``) thành từng
    giá trị để verifier chặn: lộ bất kỳ phần nào cũng là lộ đáp án. Đáp án một biểu thức giữ nguyên.
    Bỏ phần chữ (đơn vị, ``R``) và vô cực."""
    from app.generation.math_text import math_runs

    if not re.search(r"[;{}|<>\\,]", reference_answer) and len(math_runs(reference_answer)) == 1:
        return (reference_answer,)
    forms = []
    for part in re.split(r"[;{}|<>\\,]", reference_answer):
        part = part.strip().replace("+inf", "").replace("-inf", "").strip()
        while part[:1] in ("(", "[") and part.count("(") + part.count("[") > part.count(")") + part.count("]"):
            part = part[1:].strip()
        while part[-1:] in (")", "]") and part.count(")") + part.count("]") > part.count("(") + part.count("["):
            part = part[:-1].strip()
        if not re.search(r"\d", part) or part in forms:
            continue
        if len(math_runs(part)) == 1:
            forms.append(part)
    return tuple(forms)


def checkable_answer_forms(task: dict, reference_answer: str) -> tuple[str, ...] | None:
    """Các giá trị của đáp án mà verifier so được, chỉ khi chúng phủ hết đáp án; nếu không thì ``None``.

    Không phủ hết khi đáp án có phần bằng chữ hoặc dấu mà verifier không đọc được trong câu:
    ``khong-phai-ham-mu`` và tập xác định ``R`` của hàm mũ, dấu so sánh hai phân số (``<``: câu "nhỏ hơn"
    lộ đáp án mà không có số nào), tập nghiệm rỗng ``{}`` (câu "phương trình vô nghiệm"), điều kiện của
    ẩn trong bài lập phương trình (``positive_integer``: câu "x là số nguyên dương"), nghiệm chứa căn
    (verifier chưa đọc được ``sqrt``)."""
    kind = task["kind"]
    if "sqrt" in reference_answer or kind in ("fraction_compare", "word_equation"):
        return None
    if re.search(r"\{\s*\}", reference_answer):
        return None
    if kind == "exponent_numeric" and task["expression"].split(";")[0].strip() in ("base", "function"):
        return None
    forms = answer_forms(reference_answer)
    return forms or None


@dataclass(frozen=True)
class ApprovedProblem:
    ref: ProblemRef
    prompt: str
    validator_task: dict
    source_group: str
    reference_answer: str


@dataclass(frozen=True)
class ApprovedChunk:
    content: RetrievedContent
    family_id: str | None
    source_group: str | None
    lineage_ids: frozenset[str]


class ApprovedContent:
    """Bài và nội dung dạy đã duyệt. Mọi hàm trả về dữ liệu công khai, trừ ``validator_task`` và
    ``answer_key`` (chỉ validator và verifier được đọc)."""

    def __init__(self, problems: dict[str, ApprovedProblem], chunks: list[ApprovedChunk]):
        self.problems = problems
        self.chunks = chunks

    # ----------------------------------------------------------------- problem bank
    def problem_ref(self, problem_id: str) -> ProblemRef:
        return self.problems[problem_id].ref

    def problem_prompt(self, problem_id: str) -> str | None:
        problem = self.problems.get(problem_id)
        return problem.prompt if problem else None

    def validator_task(self, problem_id: str) -> dict | None:
        problem = self.problems.get(problem_id)
        return dict(problem.validator_task) if problem else None

    def counts_as_evidence(self, problem_id: str) -> bool:
        """Cùng luật với web (``tutor.outcome_eligibility``): bài chỉ chấm đáp án cuối không tạo BKT
        observation. 13 pack Member 2 đều ở chế độ này, nên Agent không cập nhật mastery từ chúng."""
        from app.assessment_modes import ASSESSMENT_MODE

        problem = self.problems.get(problem_id)
        return problem is not None and problem.validator_task.get("assessment_mode") != ASSESSMENT_MODE

    def answer_key(self, problem_id: str) -> AnswerKey | None:
        """Bộ đáp án để verifier chặn lộ đáp án, hoặc ``None`` khi chưa kiểm được đầy đủ (đáp án bằng chữ,
        nghiệm chứa căn). Khi ``None``, responder không gọi LLM (``answer_key_missing``) và chỉ dùng câu
        template, vốn không nêu đáp án."""
        problem = self.problems.get(problem_id)
        if problem is None:
            return None
        forms = checkable_answer_forms(problem.validator_task["task"], problem.reference_answer)
        return AnswerKey(problem_id, forms) if forms else None

    def candidates(self, concept_ids: list[str]) -> list[ProblemRef]:
        """Bài ứng viên theo thứ tự concept được ưu tiên (bài đang học, prerequisite, concept kế tiếp)."""
        order = {concept: index for index, concept in enumerate(dict.fromkeys(concept_ids))}
        refs = [p.ref for p in self.problems.values() if p.ref.concept_id in order]
        refs.sort(key=lambda r: (order[r.concept_id], r.difficulty, r.problem_id))
        return refs[:MAX_PROBLEMS]

    # ----------------------------------------------------------------- RAG
    def retrieve(self, skills: set[str], current_problem_id: str, primary: str | None = None, *,
                 max_level: int = MAX_HINT_LEVEL) -> list[RetrievedContent]:
        """Nội dung của các skill cho trước, mức tiết lộ không quá ``max_level``; skill ``primary`` xếp trước.
        Lọc trước khi trả, như ``allowed_hint_level`` của công cụ KB trên DB: Agent không nhận nội dung
        vượt mức mà gate cho phép ở lượt này."""
        current = self.problems.get(current_problem_id)
        blocked = {current.ref.template_family_id, current.source_group} if current else set()
        items = []
        for chunk in self.chunks:
            if chunk.content.skill_id not in skills or chunk.content.disclosure_level > max_level:
                continue
            if chunk.content.content_type == "example" and (
                    chunk.family_id in blocked or chunk.source_group in blocked or chunk.lineage_ids & blocked):
                continue  # ví dụ cùng họ với bài đang làm có thể lộ cách giải
            items.append(chunk.content)
        items.sort(key=lambda c: (c.skill_id != primary, c.disclosure_level, c.content_id))
        return items[:MAX_RETRIEVED]


def _skill(skill_ids: list[str]) -> str:
    if len(skill_ids) != 1:
        raise ValueError("Each approved concept is expected to have exactly one skill")
    return skill_ids[0]


@lru_cache(maxsize=1)
def load_approved_content() -> ApprovedContent:
    """Nạp 13 pack đã duyệt và KB chiếu từ chúng; mọi bước kiểm checksum và duyệt nằm ở code Member 2."""
    from app import kb_projection
    from app.authoring_runs import load_authoring_source
    from app.member2_runtime import demo_catalog

    _, bank = load_authoring_source("member2-v2")
    answers = {case.case_id: case.reference_answer for pack in bank.packs for case in pack.problems}
    problems = {}
    for (problem_id, version), item in demo_catalog().items():
        public = item.public
        ref = ProblemRef(problem_id=problem_id, problem_version=version, concept_id=public["concept_id"],
                         target_skill_id=public["primary_skill_id"], template_family_id=public["family_id"],
                         difficulty=DIFFICULTY[public["difficulty"]])
        problems[problem_id] = ApprovedProblem(ref, public["prompt"], dict(item.private), item.source_group,
                                               answers[problem_id])

    registry, kb_bank, origin = kb_projection.load_source("member2-v2")
    projection = kb_projection.project(registry, kb_bank, kb_projection.load_profile(), origin=origin,
                                       examples=kb_projection.load_example_publications("member2-v2"))
    chunks = []
    for chunk in projection.chunks:
        level = 4 if chunk.kind == "explanation" else chunk.hint_level
        content = RetrievedContent(content_id=chunk.content_id, skill_id=_skill(chunk.skill_ids),
                                   content_type=CONTENT_TYPE[chunk.kind], disclosure_level=level, text=chunk.text)
        chunks.append(ApprovedChunk(content, chunk.family_id, chunk.source_group,
                                    frozenset(chunk.lineage_ids or ())))
    return ApprovedContent(problems, chunks)


@dataclass
class ApprovedTools:
    """Tools của Agent trên nội dung thật: KG (registry), RAG (KB đã duyệt) và problem bank đã duyệt.
    Cùng ngân sách tool call và cùng cách tắt KG/RAG cho ablation như ``stubs.StubTools``."""

    content: ApprovedContent = field(default_factory=load_approved_content)
    kg: KGTool = field(default_factory=lambda: KGTool(include_drafts=True))

    def __call__(self, state: StudentState, config: DecisionConfig) -> TurnContext:
        kg = config.configuration != ExperimentConfiguration.NO_KG
        rag = config.configuration != ExperimentConfiguration.NO_RAG
        calls, retrieved, found = 0, [], None
        if kg:
            calls += 1
            found = self.kg(state.current.concept_id)
        edges = found.edges if found else []
        if rag:
            calls += 1
            # Gate G02: hành động trợ giúp chỉ được lên tối đa một mức so với mức hiện tại.
            allowed = min(state.support.hint_level + 1, MAX_HINT_LEVEL)
            retrieved = self.content.retrieve(retrieval_skills(state, edges), state.current.problem_id,
                                              primary=state.current.target_skill_id, max_level=allowed)
        calls += 1
        prerequisites = [e.source_concept_id for e in edges if e.depth == 1]
        next_concepts = [n.concept_id for n in found.next_concepts] if found else []
        problems = self.content.candidates([state.current.concept_id, *prerequisites, *next_concepts])
        return TurnContext(current_problem_prompt=self.content.problem_prompt(state.current.problem_id),
                           retrieved=retrieved, edges=edges, problems=problems, tool_calls_used=calls,
                           next_concepts=found.next_concepts if found else [],
                           kg_source=found.source if found else None,
                           graph_version=found.graph_version if found else None,
                           tool_errors=found.errors if found else [], kg_enabled=kg, rag_enabled=rag)


def approved_services(content: ApprovedContent | None = None, **overrides):
    """``Services`` của graph chạy trên nội dung đã duyệt thay cho bài mẫu và RAG giả."""
    from app import math_validator
    from app.agent.graph import Services
    from app.agent.observation import KnowledgeObserver
    from app.agent.validator_analyzer import ValidatorAnalyzer
    from app.generation.verifier import ResponseVerifier

    content = content or load_approved_content()
    defaults = dict(analyzer=ValidatorAnalyzer(content.validator_task, validate=math_validator.validate_bounded),
                    tools=ApprovedTools(content), verifier=ResponseVerifier(content.answer_key),
                    observer=KnowledgeObserver(counts_as_evidence=content.counts_as_evidence),
                    problem_ref=content.problem_ref, problem_prompt=content.problem_prompt)
    return Services(**{**defaults, **overrides})


# --------------------------------------------------------------------------- tra cứu chung

def _is_demo(problem_id: str) -> bool:
    from app.agent.stubs import DEMO_PROBLEMS
    return problem_id in DEMO_PROBLEMS


def any_answer_key(problem_id: str) -> AnswerKey | None:
    """Bộ đáp án cho verifier khi bộ tình huống có thể là bài mẫu hoặc bài đã duyệt (đánh giá, ablation).
    Bài mẫu không cần nạp kho đã duyệt."""
    from app.agent.stubs import demo_answer_key
    return demo_answer_key(problem_id) if _is_demo(problem_id) else load_approved_content().answer_key(problem_id)


def any_problem_prompt(problem_id: str) -> str | None:
    from app.agent.stubs import problem_prompt
    return problem_prompt(problem_id) if _is_demo(problem_id) else load_approved_content().problem_prompt(problem_id)


def reference_answers(problem_id: str) -> list[str]:
    """Đáp án hiển thị cho người chấm. Bài đã duyệt: nguyên đáp án gốc, vì các giá trị tách cho verifier
    làm mất thông tin (``[-7,+inf)`` chỉ còn ``-7``: không biết phía nào, có lấy đầu mút không). Bài mẫu:
    các dạng đáp án của verifier."""
    if not _is_demo(problem_id):
        problem = load_approved_content().problems.get(problem_id)
        return [problem.reference_answer] if problem else []
    key = any_answer_key(problem_id)
    return list(key.final_answers) if key else []
