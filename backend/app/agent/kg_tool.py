"""Tool Knowledge Graph của Agent: prerequisite 1–2 tầng và concept kế tiếp của một concept.

Thứ tự phục vụ: Neo4j (nếu được cấu hình) → bản đọc từ registry. Neo4j lỗi, chưa đồng bộ hoặc
đồng bộ bản cũ thì lượt vẫn chạy bằng bản đọc từ file và lỗi được ghi vào ``errors`` (đi vào
``tool_errors`` của decision log). Sau một lần lỗi, tool nghỉ gọi Neo4j trong ``cooldown_seconds``
để các lượt sau không phải chờ timeout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import time
from typing import Callable, Literal

from app.agent.decision import MAX_CONTEXT_EDGES
from app.agent.tools import MAX_NEXT_CONCEPTS, GraphEdge, NextConcept
from app.kg.graph import KnowledgeGraph, Neighbourhood, UnknownConcept


@lru_cache(maxsize=1)
def default_graph() -> KnowledgeGraph:
    return KnowledgeGraph.load()


@dataclass(frozen=True)
class KGLookup:
    edges: list[GraphEdge] = field(default_factory=list)
    next_concepts: list[NextConcept] = field(default_factory=list)
    source: Literal["neo4j", "registry_file"] | None = None
    graph_version: str | None = None
    errors: list[str] = field(default_factory=list)


class KGTool:
    """``include_drafts=False`` (mặc định) chỉ trả cạnh đã có người duyệt. Bật True là lựa chọn
    tường minh cho dev/đánh giá nội bộ khi registry còn nháp; mỗi cạnh trả về vẫn mang
    ``review_status`` nên decision log cho thấy quyết định dựa trên cạnh nháp."""

    def __init__(self, graph: KnowledgeGraph | None = None, neo4j=None, *, include_drafts: bool = False,
                 cooldown_seconds: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.graph = graph or default_graph()
        self.neo4j = neo4j
        self.include_drafts = include_drafts
        self._cooldown, self._clock, self._retry_at = cooldown_seconds, clock, 0.0

    @property
    def graph_version(self) -> str:
        return self.graph.version

    def _from_neo4j(self, concept_id: str, errors: list[str]) -> Neighbourhood | None:
        if self.neo4j is None or self._clock() < self._retry_at:
            return None
        try:
            found = self.neo4j.neighbourhood(concept_id, include_drafts=self.include_drafts)
        except UnknownConcept:  # registry có concept này mà Neo4j không có: Neo4j giữ bản cũ
            errors.append("kg_neo4j:stale_sync")
        except Exception as error:  # Neo4j không được làm hỏng lượt dạy
            errors.append(f"kg_neo4j:{type(error).__name__}")
        else:
            if found.fingerprint == self.graph.fingerprint:
                return found
            errors.append("kg_neo4j:stale_sync")  # Neo4j đang giữ bản registry khác bản trên đĩa
        self._retry_at = self._clock() + self._cooldown
        return None

    def __call__(self, concept_id: str) -> KGLookup:
        errors: list[str] = []
        if concept_id not in self.graph.concepts:  # registry là nguồn chuẩn về danh mục concept
            return KGLookup(graph_version=self.graph_version, errors=["kg:unknown_concept"])
        found = self._from_neo4j(concept_id, errors)
        source = "neo4j" if found is not None else "registry_file"
        if found is None:
            found = self.graph.neighbourhood(concept_id, include_drafts=self.include_drafts)
        if len(found.prerequisites) > MAX_CONTEXT_EDGES or len(found.next_concepts) > MAX_NEXT_CONCEPTS:
            errors.append("kg:truncated")  # prerequisite đã xếp tầng 1 trước nên tầng 2 bị cắt trước
        edges = [GraphEdge(edge_id=e.edge_id, source_concept_id=e.source_concept_id,
                           target_concept_id=e.target_concept_id, source_skill_ids=list(e.source_skill_ids),
                           depth=e.depth, review_status=e.review_status)
                 for e in found.prerequisites[:MAX_CONTEXT_EDGES]]
        following = [NextConcept(concept_id=n.concept_id, skill_ids=list(n.skill_ids), edge_id=n.edge_id,
                                 review_status=n.review_status,
                                 other_prerequisite_skill_ids=list(n.other_prerequisite_skill_ids))
                     for n in found.next_concepts[:MAX_NEXT_CONCEPTS]]
        return KGLookup(edges, following, source, self.graph_version, errors)
