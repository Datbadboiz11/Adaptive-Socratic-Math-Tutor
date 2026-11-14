"""Knowledge Graph: kiểm tra registry, truy vấn 1–2 tầng, tool của Agent và bản Neo4j.

Test Neo4j chỉ chạy khi đặt RUN_NEO4J_TESTS=1 (cần `docker compose --profile kg up -d neo4j`).
"""
import copy
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent.decision import MAX_CONTEXT_EDGES  # noqa: E402
from app.agent.kg_tool import KGTool  # noqa: E402
from app.kg.graph import (  # noqa: E402
    GraphInvalid, KnowledgeGraph, Registry, UnknownConcept, check_registry, fingerprint,
)

APPROVED = {"status": "human_approved", "human_reviewer": "GV. Test", "reviewed_at": "2026-11-14T09:00:00+07:00"}
DRAFT = {"status": "draft"}


def concept(concept_id, grade=6, review=DRAFT):
    return {"concept_id": concept_id, "title": f"Concept {concept_id}", "strand": "numbers",
            "skills": [{"skill_id": f"SK-{concept_id}"}], "alignment": {"grade_levels": [grade]}, "review": review}


def edge(source, target, review=DRAFT, **extra):
    return {"edge_id": f"PRE-{source}-{target}", "source_concept_id": source, "target_concept_id": target,
            "relation": "PREREQUISITE_OF", "rationale": f"{source} trước {target}", "source_id": "SRC",
            "review": review, **extra}


def registry(edges, concepts="ABCD", **concept_kw) -> Registry:
    return Registry.model_validate({
        "schema_version": "1.0.0", "content_version": "test", "sources": [{"source_id": "SRC"}],
        "concepts": [c if isinstance(c, dict) else concept(c, **concept_kw) for c in concepts], "edges": edges})


def codes(reg, severity="error"):
    return {i.code for i in check_registry(reg) if i.severity == severity}


@pytest.fixture(scope="module")
def real():
    return KnowledgeGraph.load()


# ---------------------------------------------------------------- kiểm tra khi nạp (FR08-AC1)

def test_real_registry_loads_as_dag(real):
    assert len(real.concepts) == 40 and len(real.edges) == 68
    assert not [i for i in real.warnings if i.severity == "error"]
    assert all(real.status(e.edge_id) == "draft" for e in real.edges)  # chưa có cạnh nào được duyệt


@pytest.mark.parametrize("edges,code", [
    ([edge("A", "Z")], "unknown_concept"),
    ([edge("A", "A")], "self_loop"),
    ([edge("A", "B"), edge("B", "A")], "reversed_edge"),
    ([edge("A", "B"), edge("B", "C"), edge("C", "A")], "cycle"),
    ([edge("A", "B"), edge("A", "B")], "duplicate_edge_id"),
    ([edge("A", "B"), edge("A", "B", edge_id="PRE-X")], "duplicate_edge"),
    ([edge("A", "B", edge_id="PRE-B-A")], "edge_id_direction_mismatch"),
    ([edge("A", "B", source_id="SRC-MISSING")], "unknown_source"),
    ([edge("A", "B", review={"status": "human_approved"})], "approved_without_reviewer"),
])
def test_invalid_graphs_are_rejected(edges, code):
    reg = registry(edges)
    assert code in codes(reg)
    with pytest.raises(GraphInvalid) as error:
        KnowledgeGraph(reg)
    assert code in {i.code for i in error.value.issues}


def test_duplicate_ids_and_missing_skill_are_errors():
    assert "duplicate_concept_id" in codes(registry([], concepts="AAB"))
    assert "concept_without_skill" in codes(registry([], concepts=[{**concept("A"), "skills": []}]))


def test_cycle_message_names_the_path():
    issues = check_registry(registry([edge("A", "B"), edge("B", "C"), edge("C", "A")]))
    assert any(i.code == "cycle" and "A → B → C → A" in i.message for i in issues)


def test_review_warnings_do_not_block_loading():
    reg = registry([edge("A", "B"), edge("B", "C"), edge("A", "C"), edge("D", "A")],
                   concepts=[concept("A"), concept("B"), concept("C"), concept("D", grade=9)])
    found = codes(reg, "warning")
    assert {"transitive_redundant", "grade_order", "not_approved"} <= found
    assert not codes(reg)
    KnowledgeGraph(reg)


# ---------------------------------------------------------------- truy vấn (FR08-AC2)

def test_prerequisites_one_and_two_levels(real):
    edges = real.prerequisites("E02", include_drafts=True)
    assert [e.edge_id for e in edges if e.depth == 1] == ["PRE-A02-E02", "PRE-A03-E02", "PRE-E01-E02"]
    second = [e for e in edges if e.depth == 2]
    assert {e.target_concept_id for e in second} == {"A02", "A03", "E01"} and len(second) == 6
    assert next(e for e in edges if e.edge_id == "PRE-A02-E02").source_skill_ids == ("SK-A02-DISTRIBUTE",)
    assert all(e.depth == 1 for e in real.prerequisites("E02", 1, include_drafts=True))
    assert real.prerequisites("N01", include_drafts=True) == []  # concept gốc


def test_query_guards(real):
    with pytest.raises(UnknownConcept):
        real.prerequisites("Z99", include_drafts=True)
    with pytest.raises(ValueError):
        real.prerequisites("E02", 3, include_drafts=True)


def test_successors_list_other_prerequisites(real):
    following = {n.concept_id: n for n in real.successors("E02", include_drafts=True)}
    assert set(following) == {"E03", "E04", "E05", "E08", "E09", "F04"}
    assert following["E03"].edge_id == "PRE-E02-E03"
    assert following["E03"].other_prerequisite_skill_ids == ("SK-A01-EVALUATE",)
    assert real.successors("F10", include_drafts=True) == []


def test_drafts_are_hidden_by_default(real):
    assert real.prerequisites("E02") == [] and real.successors("E02") == []


def test_approved_only_needs_edge_and_both_concepts_approved():
    reg = registry([edge("A", "B", APPROVED), edge("B", "C", APPROVED), edge("D", "C", APPROVED)],
                   concepts=[concept("A", review=APPROVED), concept("B", review=APPROVED),
                             concept("C", review=APPROVED), concept("D")])
    graph = KnowledgeGraph(reg)
    assert graph.status("PRE-D-C") == "draft"  # concept D còn nháp nên cạnh chưa dùng được
    assert [(e.edge_id, e.depth) for e in graph.prerequisites("C")] == [("PRE-B-C", 1), ("PRE-A-B", 2)]
    assert len(graph.prerequisites("C", include_drafts=True)) == 3
    assert [n.concept_id for n in graph.successors("A")] == ["B"]
    # Tầng 2 chỉ đi qua tầng 1 nhìn thấy được.
    hidden = registry([edge("A", "B", APPROVED), edge("B", "C")], concepts=[concept(c, review=APPROVED) for c in "ABC"])
    assert KnowledgeGraph(hidden).prerequisites("C") == []


def test_fingerprint_tracks_content():
    edges = [edge("A", "B")]
    assert fingerprint(registry(edges)) == fingerprint(registry(copy.deepcopy(edges)))
    assert fingerprint(registry(edges)) != fingerprint(registry([edge("A", "B", APPROVED)]))
    assert fingerprint(registry(edges)) != fingerprint(registry(edges + [edge("B", "C")]))


# ---------------------------------------------------------------- tool của Agent

def test_tool_returns_contract_objects_within_limits(real):
    tool = KGTool(real, include_drafts=True)
    for concept_id in real.concepts:
        found = tool(concept_id)
        assert found.errors == [] and found.source == "registry_file", concept_id
        assert len(found.edges) <= MAX_CONTEXT_EDGES
        assert all(e.review_status == "draft" for e in found.edges)
    assert tool("E02").graph_version == real.version


def test_tool_is_approved_only_unless_asked(real):
    assert KGTool(real)("E02").edges == [] and KGTool(real)("E02").next_concepts == []


def test_tool_reports_unknown_concept(real):
    found = KGTool(real, include_drafts=True)("CON-LINEAR-01")
    assert found.edges == [] and found.errors == ["kg:unknown_concept"] and found.source is None


class FakeNeo4j:
    def __init__(self, graph, *, fail=False, stale=False):
        self.graph, self.fail, self.stale, self.calls = graph, fail, stale, 0

    def neighbourhood(self, concept_id, *, include_drafts=False):
        self.calls += 1
        if self.fail:
            raise ConnectionError("neo4j down")
        found = self.graph.neighbourhood(concept_id, include_drafts=include_drafts)
        return found if not self.stale else type(found)(found.prerequisites, found.next_concepts, "old", "old")


def test_tool_prefers_neo4j_when_in_sync(real):
    found = KGTool(real, FakeNeo4j(real), include_drafts=True)("E02")
    assert found.source == "neo4j" and found.errors == []
    assert found.edges == KGTool(real, include_drafts=True)("E02").edges


def test_tool_falls_back_to_registry_and_backs_off(real):
    now = [0.0]
    neo4j = FakeNeo4j(real, fail=True)
    tool = KGTool(real, neo4j, include_drafts=True, cooldown_seconds=30, clock=lambda: now[0])
    found = tool("E02")
    assert found.source == "registry_file" and found.errors == ["kg_neo4j:ConnectionError"]
    assert len(found.edges) == 9
    assert tool("E02").errors == [] and neo4j.calls == 1  # đang nghỉ: không gọi Neo4j, không chờ timeout
    now[0] = 31.0
    neo4j.fail = False
    assert tool("E02").source == "neo4j" and neo4j.calls == 2


def test_tool_rejects_stale_neo4j(real):
    found = KGTool(real, FakeNeo4j(real, stale=True), include_drafts=True)("E02")
    assert found.source == "registry_file" and found.errors == ["kg_neo4j:stale_sync"]


# ---------------------------------------------------------------- bảng rà soát cạnh

sys.path.insert(0, str(ROOT / "scripts" / "checks"))
import check_kg  # noqa: E402

DECISION, BASIS = check_kg.REVIEW_COLUMNS[0], check_kg.REVIEW_COLUMNS[1]


def worksheet_rows(path, delimiter=","):
    import csv

    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def rewrite(path, rows, delimiter=","):
    import csv

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_regenerating_worksheet_keeps_reviewer_columns(real, tmp_path, delimiter):
    # Review P2: xuất lại từng ghi đè toàn bộ nội dung người duyệt đã điền.
    target = tmp_path / "review.csv"
    assert check_kg.write_worksheet(real.registry, real.warnings, target) == {"edges": 68, "preserved": 0, "orphans": 0}
    rows = worksheet_rows(target)
    rows[0].update({DECISION: "giu", BASIS: "CT 2018, lớp 7; trang 52", "nguoi_duyet": "GV. A"})
    rows.append({**dict.fromkeys(rows[0], ""), "edge_id": "PRE-OLD-EDGE", DECISION: "bo", "ghi_chu": "đã gỡ"})
    rewrite(target, rows, delimiter)  # Excel có thể lưu lại bằng dấu chấm phẩy
    assert check_kg.write_worksheet(real.registry, real.warnings, target) == {"edges": 68, "preserved": 1, "orphans": 1}
    again = worksheet_rows(target)
    first = next(r for r in again if r["edge_id"] == rows[0]["edge_id"])
    assert (first[DECISION], first[BASIS], first["nguoi_duyet"]) == ("giu", "CT 2018, lớp 7; trang 52", "GV. A")
    orphan = again[-1]
    assert (orphan["edge_id"], orphan["trang_thai_hien_tai"], orphan["ghi_chu"]) == \
        ("PRE-OLD-EDGE", "removed_from_registry", "đã gỡ")
    assert not list(tmp_path.glob("*.tmp"))


def test_unreadable_worksheet_is_never_overwritten(real, tmp_path):
    target = tmp_path / "review.csv"
    for content in ("cot_la,cot_khac\n1,2\n".encode("utf-8"), "edge_id,ghi_chú\nPRE-A-B,đã duyệt\n".encode("utf-16")):
        target.write_bytes(content)
        with pytest.raises(check_kg.WorksheetUnreadable):
            check_kg.write_worksheet(real.registry, real.warnings, target)
        assert target.read_bytes() == content


# ---------------------------------------------------------------- Neo4j thật

neo4j_only = pytest.mark.skipif(not os.environ.get("RUN_NEO4J_TESTS"),
                                reason="Neo4j integration requires RUN_NEO4J_TESTS=1")


@pytest.fixture
def store(real):
    from app.kg.neo4j_store import Neo4jGraph

    graph = Neo4jGraph.from_env({"NEO4J_URI": "bolt://127.0.0.1:7687", **os.environ}, timeout=10.0)
    yield graph
    graph.sync(real)  # test ghi đồ thị giả; trả Neo4j về đúng bản registry thật
    graph.close()


def same(graph, store):
    return all(store.neighbourhood(c, include_drafts=d) == graph.neighbourhood(c, include_drafts=d)
               for c in graph.concepts for d in (False, True))


@neo4j_only
def test_neo4j_matches_registry_on_every_concept(real, store):
    meta = store.sync(real)
    assert (meta["concepts"], meta["edges"]) == (40, 68) and store.meta()["fingerprint"] == real.fingerprint
    assert same(real, store)
    assert store.prerequisites("E02", 1, include_drafts=True) == real.prerequisites("E02", 1, include_drafts=True)
    with pytest.raises(UnknownConcept):
        store.neighbourhood("Z99")


@neo4j_only
def test_neo4j_review_filter_and_resync_removes_stale_data(store):
    reviewed = [concept(c, review=APPROVED) for c in "ABC"] + [concept("D")]
    first = KnowledgeGraph(registry([edge("A", "B", APPROVED), edge("B", "C", APPROVED), edge("D", "C", APPROVED),
                                     edge("A", "C")], concepts=reviewed))
    store.sync(first)
    assert same(first, store)
    assert [(e.edge_id, e.depth) for e in store.prerequisites("C")] == [("PRE-B-C", 1), ("PRE-A-B", 2)]
    second = KnowledgeGraph(registry([edge("A", "B", APPROVED)], concepts=reviewed[:2]))
    store.sync(second)
    assert same(second, store) and store.meta()["concepts"] == 2
    with pytest.raises(UnknownConcept):  # concept C đã bị gỡ khỏi registry
        store.neighbourhood("C")


@neo4j_only
def test_tool_serves_from_real_neo4j(real, store):
    store.sync(real)
    found = KGTool(real, store, include_drafts=True)("E02")
    assert found.source == "neo4j" and found.errors == []
    assert found.edges == KGTool(real, include_drafts=True)("E02").edges
    stale = KnowledgeGraph(registry([edge("A", "B")]))
    assert KGTool(stale, store, include_drafts=True)("A").errors == ["kg_neo4j:stale_sync"]


@neo4j_only
def test_full_session_decides_from_real_neo4j(real, store):
    from uuid import uuid4

    from app.agent.decision import DecisionConfig
    from app.agent.graph import Services, TurnInput, TutorEngine
    from app.agent.stubs import StubTools

    store.sync(real)
    engine = TutorEngine(DecisionConfig(configuration="rule_policy", policy_version="rule-policy-0.2.0"),
                         Services(tools=StubTools(kg=KGTool(real, store, include_drafts=True))))
    sid = engine.start("demo-a", "E02-P001").session_id
    wrong = ["2x - 3 = 10", "2x = 13", "x = 6.5"]
    turns = [("submit", wrong), ("submit", wrong), ("request_hint", []), ("request_hint", []), ("submit", wrong)]
    replies = [engine.turn(sid, TurnInput(request_id=uuid4(), trigger=trigger, steps=steps))
               for trigger, steps in turns]
    assert replies[-1].action == "backtrack"
    records = engine.decisions(sid)
    assert all(r.kg_source == "neo4j" and not r.tool_errors for r in records)
    assert records[-1].final.edge_ids == ["PRE-A02-E02"]
