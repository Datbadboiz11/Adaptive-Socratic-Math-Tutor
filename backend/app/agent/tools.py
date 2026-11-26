"""Kết quả tool trong một lượt mà Agent và policy gate được thấy.

RAG/KG/problem bank không nằm trong StudentState: chúng là kết quả gọi tool của lượt hiện tại.
Gate đối chiếu content_ids/edge_ids/problem_id của quyết định với các danh sách ở đây
(PRD FR09-AC2/3: không gắn nguồn chưa được truy xuất).
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.agent.decision import MAX_CONTEXT_EDGES, MAX_TOOL_CALLS, Contract, HintLevel, Identifier


class RetrievedContent(Contract):
    """Một mục nội dung đã duyệt được đưa vào context.

    ``disclosure_level`` là mức hint thấp nhất được phép hiển thị nội dung này: nội dung có
    mức tiết lộ 4 chỉ dùng được trong phản hồi mức 4. Không bao giờ chứa lời giải bài đang làm."""

    content_id: Identifier
    skill_id: Identifier
    content_type: Literal["question", "hint", "explanation", "example", "template"]
    disclosure_level: HintLevel
    text: str = Field(min_length=1, max_length=1200)


ReviewStatus = Literal["draft", "machine_checked", "human_approved"]
MAX_NEXT_CONCEPTS = 12


class GraphEdge(Contract):
    """Cạnh PREREQUISITE_OF do KG trả về: concept nguồn cần học trước concept đích.

    ``depth`` = 1 khi đích là concept đang học, = 2 khi đích là một prerequisite trực tiếp của
    nó (PRD FR08-AC2: tối đa 2 tầng). ``review_status`` cho biết cạnh đã được người duyệt chưa;
    cạnh nháp chỉ xuất hiện khi tool được bật chế độ dev một cách tường minh."""

    edge_id: Identifier
    source_concept_id: Identifier
    target_concept_id: Identifier
    source_skill_ids: list[Identifier] = Field(min_length=1)
    relation: Literal["PREREQUISITE_OF"] = "PREREQUISITE_OF"
    depth: Literal[1, 2] = 1
    review_status: ReviewStatus = "draft"


class NextConcept(Contract):
    """Concept có thể học tiếp: nhận concept đang học làm prerequisite (cạnh ``edge_id``).

    ``other_prerequisite_skill_ids`` là skill của các prerequisite trực tiếp khác của concept
    đó, để người chọn biết học sinh còn cần gì trước khi chuyển."""

    concept_id: Identifier
    skill_ids: list[Identifier] = Field(min_length=1)
    edge_id: Identifier
    review_status: ReviewStatus = "draft"
    other_prerequisite_skill_ids: list[Identifier] = Field(default_factory=list)


class ProblemRef(Contract):
    """Bài ứng viên lấy từ problem bank. Không có đáp án."""

    problem_id: Identifier
    problem_version: str
    concept_id: Identifier
    target_skill_id: Identifier
    template_family_id: Identifier
    difficulty: int = Field(ge=1, le=5)


class TurnContext(Contract):
    # Đề bài của bài đang làm, đúng như học sinh thấy (lấy từ problem bank). Chỉ là đề công khai:
    # đáp án và lời giải tham chiếu không bao giờ nằm trong context.
    current_problem_prompt: str | None = Field(default=None, min_length=1, max_length=1000)
    retrieved: list[RetrievedContent] = Field(default_factory=list, max_length=10)
    edges: list[GraphEdge] = Field(default_factory=list, max_length=MAX_CONTEXT_EDGES)
    next_concepts: list[NextConcept] = Field(default_factory=list, max_length=MAX_NEXT_CONCEPTS)
    problems: list[ProblemRef] = Field(default_factory=list, max_length=20)
    # Tổng số tool call trong lượt (kể cả của Agent). Ngân sách ≤ 3 được chặn ngay ở contract:
    # nơi gọi tool phải dừng khi hết ngân sách thay vì để gate phát hiện sau.
    tool_calls_used: int = Field(default=0, ge=0, le=MAX_TOOL_CALLS)
    kg_enabled: bool = True
    rag_enabled: bool = True
    # Nơi trả lời truy vấn KG trong lượt này và phiên bản đồ thị (content_version + dấu vân tay).
    kg_source: Literal["neo4j", "registry_file"] | None = None
    graph_version: str | None = None
    # Tool lỗi thì lượt vẫn chạy tiếp: KG rơi về bản đọc từ file, tool khác thì bỏ qua. Ghi lại để
    # đánh giá loại/đánh dấu lượt này.
    tool_errors: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=5)

    def content(self, content_id: str) -> RetrievedContent | None:
        return next((c for c in self.retrieved if c.content_id == content_id), None)

    def edge(self, edge_id: str) -> GraphEdge | None:
        return next((e for e in self.edges if e.edge_id == edge_id), None)

    def prerequisite_chain(self, edge_ids: list[str], concept_id: str) -> dict[str, int] | None:
        """Skill đi tới được từ ``concept_id`` qua các cạnh được trích, kèm số tầng (1 hoặc 2).
        Trả None nếu có cạnh không thuộc context hoặc không nối về concept đó."""
        edges = [self.edge(edge_id) for edge_id in edge_ids]
        if any(e is None for e in edges):
            return None
        skills, targets, used = {}, {concept_id}, set()
        for depth in (1, 2):
            level = [e for e in edges if e.target_concept_id in targets and e.edge_id not in used]
            used |= {e.edge_id for e in level}
            for e in level:
                for skill_id in e.source_skill_ids:
                    skills.setdefault(skill_id, depth)
            targets = {e.source_concept_id for e in level}
        return skills if len(used) == len(edges) else None

    def problem(self, problem_id: str) -> ProblemRef | None:
        return next((p for p in self.problems if p.problem_id == problem_id), None)
