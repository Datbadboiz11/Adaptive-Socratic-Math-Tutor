"""Knowledge Graph đọc từ registry (plan §8.4, PRD FR-08).

``content/curriculum/registry.v1.json`` là nguồn chuẩn; Neo4j là bản đồng bộ để truy vấn
(``neo4j_store.py``). Module này chỉ đọc các trường KG cần, tự kiểm tra đồ thị và trả kết quả
truy vấn cùng kiểu với bản Neo4j, nên dùng làm dự phòng khi Neo4j không chạy.

Quy ước cạnh: ``PREREQUISITE_OF`` hướng A → B nghĩa là A cần học trước B.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

REGISTRY_PATH = Path(__file__).resolve().parents[3] / "content" / "curriculum" / "registry.v1.json"
PREREQUISITE = "PREREQUISITE_OF"
RELATIONS = ("PREREQUISITE_OF", "RELATED_TO", "PART_OF")
ReviewStatus = Literal["draft", "machine_checked", "human_approved"]
STATUS_RANK = {"draft": 0, "machine_checked": 1, "human_approved": 2}
MAX_DEPTH = 2
_EDGE_ID = re.compile(r"^PRE-([A-Za-z0-9]+)-([A-Za-z0-9]+)$")


# --------------------------------------------------------------------------- dữ liệu registry

class _Row(BaseModel):
    """Chỉ đọc trường KG cần; trường khác của registry (authoring) được bỏ qua."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Review(_Row):
    status: ReviewStatus
    human_reviewer: str | None = None
    reviewed_at: str | None = None


class Skill(_Row):
    skill_id: str
    observable_behavior: str = ""


class Alignment(_Row):
    grade_levels: tuple[int, ...] = ()
    source_id: str | None = None


class Concept(_Row):
    concept_id: str
    title: str
    strand: str
    objective: str = ""
    skills: tuple[Skill, ...] = ()
    alignment: Alignment = Alignment()
    pilot: bool = False
    review: Review

    @property
    def skill_ids(self) -> tuple[str, ...]:
        return tuple(s.skill_id for s in self.skills)


class Edge(_Row):
    edge_id: str
    source_concept_id: str
    target_concept_id: str
    relation: Literal["PREREQUISITE_OF", "RELATED_TO", "PART_OF"]
    rationale: str = ""
    source_id: str | None = None
    review: Review


class Source(_Row):
    source_id: str
    title: str = ""
    url: str = ""


class Registry(_Row):
    schema_version: str
    content_version: str
    sources: tuple[Source, ...] = ()
    concepts: tuple[Concept, ...]
    edges: tuple[Edge, ...]


def read_registry(path: Path = REGISTRY_PATH) -> Registry:
    return Registry.model_validate_json(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- kiểm tra đồ thị

@dataclass(frozen=True)
class Issue:
    """``error`` chặn việc dùng và đồng bộ đồ thị (FR08-AC1); ``warning`` là việc cho người duyệt."""

    severity: Literal["error", "warning"]
    code: str
    message: str
    ids: tuple[str, ...] = ()


class GraphInvalid(ValueError):
    def __init__(self, issues: list[Issue]):
        super().__init__("; ".join(f"{i.code}: {i.message}" for i in issues))
        self.issues = issues


class UnknownConcept(KeyError):
    pass


def _cycles(nodes, outgoing) -> list[list[str]]:
    """Mỗi cạnh ngược gặp trong DFS cho một chu trình (danh sách concept theo thứ tự đi)."""
    state, stack, found = {}, [], []

    def visit(node):
        state[node] = 1
        stack.append(node)
        for nxt in outgoing[node]:
            if state.get(nxt) == 1:
                found.append(stack[stack.index(nxt):] + [nxt])
            elif nxt not in state:
                visit(nxt)
        stack.pop()
        state[node] = 2

    for node in nodes:
        if node not in state:
            visit(node)
    return found


def _approval_issue(kind, item_id, review: Review) -> Issue | None:
    if review.status == "human_approved" and not (review.human_reviewer and review.reviewed_at):
        return Issue("error", "approved_without_reviewer",
                     f"{kind} {item_id} ghi human_approved nhưng thiếu người duyệt hoặc thời điểm duyệt", (item_id,))
    return None


def check_registry(reg: Registry) -> list[Issue]:
    """Kiểm tra khi nạp registry: ID trùng/thiếu, tự trỏ, cạnh đảo chiều, chu trình (lỗi) và
    các điểm người duyệt cần xem (cảnh báo). Cảnh báo chỉ tính khi không còn lỗi."""
    issues: list[Issue] = []

    def error(code, message, *ids):
        issues.append(Issue("error", code, message, tuple(ids)))

    for name, values in (("concept_id", [c.concept_id for c in reg.concepts]),
                         ("skill_id", [s.skill_id for c in reg.concepts for s in c.skills]),
                         ("edge_id", [e.edge_id for e in reg.edges]),
                         ("source_id", [s.source_id for s in reg.sources])):
        for value, n in Counter(values).items():
            if n > 1:
                error(f"duplicate_{name}", f"{name} {value} xuất hiện {n} lần", value)

    concepts = {c.concept_id: c for c in reg.concepts}
    sources = {s.source_id for s in reg.sources}
    for c in reg.concepts:
        if not c.skills:
            error("concept_without_skill", f"Concept {c.concept_id} không có skill", c.concept_id)
        if issue := _approval_issue("Concept", c.concept_id, c.review):
            issues.append(issue)

    prerequisite: list[Edge] = []
    for e in reg.edges:
        a, b = e.source_concept_id, e.target_concept_id
        missing = [i for i in (a, b) if i not in concepts]
        if missing:
            error("unknown_concept", f"Cạnh {e.edge_id} trỏ tới concept không tồn tại: {', '.join(missing)}",
                  e.edge_id, *missing)
            continue
        if a == b:
            error("self_loop", f"Cạnh {e.edge_id} nối {a} với chính nó", e.edge_id)
            continue
        if e.source_id not in sources:
            error("unknown_source", f"Cạnh {e.edge_id} ghi nguồn không tồn tại: {e.source_id}", e.edge_id)
        if issue := _approval_issue("Cạnh", e.edge_id, e.review):
            issues.append(issue)
        if e.relation == PREREQUISITE:
            named = _EDGE_ID.match(e.edge_id)
            if named and (named[1], named[2]) != (a, b):
                error("edge_id_direction_mismatch",
                      f"Cạnh {e.edge_id} có ID không khớp chiều {a} → {b}", e.edge_id)
            prerequisite.append(e)

    for (a, b, relation), n in Counter((e.source_concept_id, e.target_concept_id, e.relation)
                                       for e in reg.edges).items():
        if n > 1:
            error("duplicate_edge", f"Có {n} cạnh {relation} cùng nối {a} → {b}", a, b)

    by_pair = {(e.source_concept_id, e.target_concept_id): e for e in prerequisite}
    for (a, b), e in by_pair.items():
        if a < b and (b, a) in by_pair:
            error("reversed_edge", f"Có cả hai chiều {a} → {b} và {b} → {a}", e.edge_id, by_pair[(b, a)].edge_id)
    outgoing = defaultdict(list)
    for e in prerequisite:
        outgoing[e.source_concept_id].append(e.target_concept_id)
    for cycle in _cycles(list(concepts), outgoing):
        if len(cycle) > 3:  # chu trình 2 đỉnh đã báo ở reversed_edge
            error("cycle", "Chu trình prerequisite: " + " → ".join(cycle), *cycle[:-1])

    if not issues:
        issues += _review_warnings(reg, concepts, prerequisite, outgoing)
    return issues


def _review_warnings(reg, concepts, prerequisite, outgoing) -> list[Issue]:
    out: list[Issue] = []

    def warn(code, message, *ids):
        out.append(Issue("warning", code, message, tuple(ids)))

    reach: dict[str, set[str]] = {}

    def reachable(node) -> set[str]:
        if node not in reach:
            reach[node] = set()
            for nxt in outgoing[node]:
                reach[node] |= {nxt} | reachable(nxt)
        return reach[node]

    linked = set()
    for e in sorted(prerequisite, key=lambda e: e.edge_id):
        a, b = e.source_concept_id, e.target_concept_id
        linked |= {a, b}
        grades_a, grades_b = concepts[a].alignment.grade_levels, concepts[b].alignment.grade_levels
        if grades_a and grades_b and min(grades_a) > min(grades_b):
            warn("grade_order", f"{e.edge_id}: {a} (lớp {min(grades_a)}) được ghi là nền của {b} (lớp {min(grades_b)})",
                 e.edge_id)
        via = sorted(m for m in outgoing[a] if m != b and b in reachable(m))
        if via:
            warn("transitive_redundant", f"{e.edge_id}: {a} → {b} đã suy ra được qua {', '.join(via)}", e.edge_id)
    for concept_id in concepts:
        if concept_id not in linked:
            warn("isolated_concept", f"Concept {concept_id} không có cạnh prerequisite nào", concept_id)

    def template(e: Edge) -> str:
        return e.rationale.replace(e.source_concept_id, "{A}").replace(e.target_concept_id, "{B}")

    shared = Counter(template(e) for e in prerequisite)
    generic = sorted(e.edge_id for e in prerequisite if shared[template(e)] > 1)
    if generic:
        warn("generic_rationale", f"{len(generic)}/{len(prerequisite)} cạnh dùng chung một câu căn cứ mẫu, "
                                  "chưa có căn cứ riêng", *generic)
    graph_status = {e.edge_id: _effective_status(e, concepts) for e in prerequisite}
    unapproved = sorted(k for k, v in graph_status.items() if v != "human_approved")
    if unapproved:
        warn("not_approved", f"{len(unapproved)}/{len(prerequisite)} cạnh prerequisite chưa được duyệt "
                             "(cạnh hoặc concept hai đầu); chế độ chỉ dùng cạnh đã duyệt sẽ không trả các cạnh này",
             *unapproved)
    return out


def _effective_status(edge: Edge, concepts: dict[str, Concept]) -> str:
    """Cạnh chỉ coi là đã duyệt khi cả cạnh và hai concept đầu mút đều đã duyệt."""
    statuses = (edge.review.status, concepts[edge.source_concept_id].review.status,
                concepts[edge.target_concept_id].review.status)
    return min(statuses, key=STATUS_RANK.__getitem__)


# --------------------------------------------------------------------------- kết quả truy vấn

@dataclass(frozen=True)
class PrerequisiteEdge:
    """Cạnh A → B trong phạm vi 1–2 tầng trước concept đang hỏi. ``depth`` = 1 khi B là concept
    đang hỏi, = 2 khi B là một prerequisite trực tiếp của nó."""

    edge_id: str
    source_concept_id: str
    target_concept_id: str
    source_skill_ids: tuple[str, ...]
    depth: int
    review_status: str


@dataclass(frozen=True)
class NextConcept:
    """Concept nhận concept đang hỏi làm prerequisite, kèm skill của các prerequisite trực tiếp
    khác của nó (để người chọn biết còn cần gì nữa)."""

    concept_id: str
    skill_ids: tuple[str, ...]
    edge_id: str
    review_status: str
    other_prerequisite_skill_ids: tuple[str, ...]


@dataclass(frozen=True)
class Neighbourhood:
    prerequisites: tuple[PrerequisiteEdge, ...]
    next_concepts: tuple[NextConcept, ...]
    content_version: str
    fingerprint: str


def fingerprint(reg: Registry) -> str:
    """Dấu vân tay nội dung đồ thị; dùng để phát hiện Neo4j chưa đồng bộ bản registry mới."""
    payload = {
        "content_version": reg.content_version,
        "concepts": sorted([c.concept_id, c.title, c.strand, c.objective, list(c.alignment.grade_levels),
                            list(c.skill_ids), c.pilot, c.review.status] for c in reg.concepts),
        "edges": sorted([e.edge_id, e.source_concept_id, e.target_concept_id, e.relation, e.rationale,
                         e.source_id or "", e.review.status, e.review.human_reviewer or "",
                         e.review.reviewed_at or ""] for e in reg.edges),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- đồ thị trong bộ nhớ

class KnowledgeGraph:
    """Đồ thị đã qua kiểm tra. Registry có lỗi thì không tạo được (``GraphInvalid``).

    Mặc định mọi truy vấn chỉ đi qua cạnh đã duyệt. ``include_drafts=True`` là lựa chọn tường
    minh cho dev/đánh giá nội bộ; kết quả luôn kèm ``review_status`` để log thấy cạnh nháp."""

    def __init__(self, registry: Registry):
        issues = check_registry(registry)
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            raise GraphInvalid(errors)
        self.registry = registry
        self.warnings = issues
        self.content_version = registry.content_version
        self.fingerprint = fingerprint(registry)
        self.concepts = {c.concept_id: c for c in registry.concepts}
        self.edges = tuple(sorted(registry.edges, key=lambda e: e.edge_id))
        self._status = {e.edge_id: _effective_status(e, self.concepts) for e in self.edges}
        self._incoming, self._outgoing = defaultdict(list), defaultdict(list)
        for e in self.edges:
            if e.relation == PREREQUISITE:
                self._incoming[e.target_concept_id].append(e)
                self._outgoing[e.source_concept_id].append(e)

    @classmethod
    def load(cls, path: Path = REGISTRY_PATH) -> "KnowledgeGraph":
        return cls(read_registry(path))

    @property
    def version(self) -> str:
        return f"{self.content_version}+{self.fingerprint[:12]}"

    def status(self, edge_id: str) -> str:
        return self._status[edge_id]

    def _visible(self, edge: Edge, include_drafts: bool) -> bool:
        return include_drafts or self._status[edge.edge_id] == "human_approved"

    def _require(self, concept_id: str) -> None:
        if concept_id not in self.concepts:
            raise UnknownConcept(concept_id)

    def prerequisites(self, concept_id: str, max_depth: int = MAX_DEPTH, *,
                      include_drafts: bool = False) -> list[PrerequisiteEdge]:
        if max_depth not in (1, 2):
            raise ValueError("Chỉ hỗ trợ truy 1 hoặc 2 tầng prerequisite")
        self._require(concept_id)
        out, targets = [], [concept_id]
        for depth in range(1, max_depth + 1):
            level = [e for t in targets for e in self._incoming[t] if self._visible(e, include_drafts)]
            out += [PrerequisiteEdge(e.edge_id, e.source_concept_id, e.target_concept_id,
                                     self.concepts[e.source_concept_id].skill_ids, depth, self._status[e.edge_id])
                    for e in level]
            targets = sorted({e.source_concept_id for e in level})
        return sorted(out, key=lambda e: (e.depth, e.edge_id))

    def successors(self, concept_id: str, *, include_drafts: bool = False) -> list[NextConcept]:
        self._require(concept_id)
        out = []
        for e in self._outgoing[concept_id]:
            if not self._visible(e, include_drafts):
                continue
            target = self.concepts[e.target_concept_id]
            others = sorted((o for o in self._incoming[target.concept_id]
                             if o.source_concept_id != concept_id and self._visible(o, include_drafts)),
                            key=lambda o: o.source_concept_id)
            out.append(NextConcept(target.concept_id, target.skill_ids, e.edge_id, self._status[e.edge_id],
                                   tuple(sk for o in others for sk in self.concepts[o.source_concept_id].skill_ids)))
        return sorted(out, key=lambda n: n.edge_id)

    def neighbourhood(self, concept_id: str, *, include_drafts: bool = False,
                      max_depth: int = MAX_DEPTH) -> Neighbourhood:
        return Neighbourhood(tuple(self.prerequisites(concept_id, max_depth, include_drafts=include_drafts)),
                             tuple(self.successors(concept_id, include_drafts=include_drafts)),
                             self.content_version, self.fingerprint)
