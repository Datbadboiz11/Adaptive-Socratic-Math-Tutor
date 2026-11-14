"""Bản Neo4j của Knowledge Graph: đồng bộ từ registry và truy vấn bằng Cypher.

Lược đồ:
    (:Concept {concept_id, title, strand, objective, grade_levels, skill_ids, pilot,
               review_status, alignment_source_id, content_version})
    (:Concept)-[:PREREQUISITE_OF | :RELATED_TO | :PART_OF
                {edge_id, rationale, source_id, review_status, effective_status,
                 human_reviewer, reviewed_at}]->(:Concept)
    (:KGMeta {id: 'registry', content_version, fingerprint, concepts, edges, synced_at})

Registry là nguồn chuẩn: ``sync`` ghi đè toàn bộ trong một transaction, nên người đọc không
bao giờ thấy đồ thị đồng bộ dở. ``neighbourhood`` trả cùng kiểu với ``KnowledgeGraph``.
Driver ``neo4j`` chỉ được import khi tạo kết nối, để phần đọc từ file không phụ thuộc nó.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os

from app.kg.graph import (
    MAX_DEPTH, RELATIONS, KnowledgeGraph, Neighbourhood, NextConcept, PrerequisiteEdge, UnknownConcept,
)

DEFAULT_URI = "bolt://127.0.0.1:7687"
DEFAULT_USER = "neo4j"
DEV_PASSWORD = "local-dev-only"  # trùng mặc định trong compose.yaml; chỉ dùng cho máy cá nhân


class GraphNotSynced(RuntimeError):
    """Neo4j chạy nhưng chưa có dữ liệu đồng bộ từ registry."""


_META = """
MATCH (m:KGMeta {id: 'registry'})
OPTIONAL MATCH (c:Concept {concept_id: $id})
RETURN m.fingerprint AS fingerprint, m.content_version AS content_version, c IS NOT NULL AS known
"""
_DEPTH_1 = """
MATCH (s:Concept)-[r:PREREQUISITE_OF]->(:Concept {concept_id: $id})
WHERE $drafts OR r.effective_status = 'human_approved'
RETURN r.edge_id AS edge_id, s.concept_id AS source, $id AS target, s.skill_ids AS skills,
       r.effective_status AS status
"""
_DEPTH_2 = """
MATCH (s:Concept)-[r2:PREREQUISITE_OF]->(m:Concept)-[r1:PREREQUISITE_OF]->(:Concept {concept_id: $id})
WHERE $drafts OR (r1.effective_status = 'human_approved' AND r2.effective_status = 'human_approved')
RETURN DISTINCT r2.edge_id AS edge_id, s.concept_id AS source, m.concept_id AS target, s.skill_ids AS skills,
       r2.effective_status AS status
"""
_SUCCESSORS = """
MATCH (cur:Concept {concept_id: $id})-[r:PREREQUISITE_OF]->(n:Concept)
WHERE $drafts OR r.effective_status = 'human_approved'
OPTIONAL MATCH (o:Concept)-[r2:PREREQUISITE_OF]->(n)
WHERE o <> cur AND ($drafts OR r2.effective_status = 'human_approved')
WITH r, n, o ORDER BY o.concept_id
RETURN r.edge_id AS edge_id, n.concept_id AS concept_id, n.skill_ids AS skills,
       r.effective_status AS status, collect(o.skill_ids) AS other
"""


class Neo4jGraph:
    def __init__(self, uri: str = DEFAULT_URI, user: str = DEFAULT_USER, password: str = DEV_PASSWORD, *,
                 database: str | None = None, timeout: float = 1.0):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=timeout,
                                            connection_acquisition_timeout=timeout)
        self._database, self._timeout = database, timeout

    @classmethod
    def from_env(cls, env=os.environ, **kwargs) -> "Neo4jGraph | None":
        """Tạo kết nối khi có ``NEO4J_URI``; không có thì trả None (chỉ dùng bản đọc từ file)."""
        uri = env.get("NEO4J_URI")
        if not uri:
            return None
        return cls(uri, env.get("NEO4J_USER", DEFAULT_USER), env.get("NEO4J_PASSWORD", DEV_PASSWORD),
                   database=env.get("NEO4J_DATABASE") or None, **kwargs)

    def close(self) -> None:
        self._driver.close()

    def _session(self):
        return self._driver.session(database=self._database)

    def _read(self, fn):
        """Đọc trong một transaction tường minh, không tự thử lại: Neo4j lỗi thì lượt dạy chuyển
        ngay sang bản đọc từ file, nên một lần gọi hỏng chỉ chờ tối đa ``timeout``."""
        with self._session() as session, session.begin_transaction(timeout=self._timeout) as tx:
            return fn(tx)

    # ----------------------------------------------------------------------- đồng bộ

    def sync(self, graph: KnowledgeGraph) -> dict:
        """Ghi toàn bộ đồ thị đã kiểm tra vào Neo4j. Concept/cạnh không còn trong registry bị xóa."""
        concepts = [{"concept_id": c.concept_id, "title": c.title, "strand": c.strand, "objective": c.objective,
                     "grade_levels": list(c.alignment.grade_levels), "skill_ids": list(c.skill_ids),
                     "pilot": c.pilot, "review_status": c.review.status,
                     "alignment_source_id": c.alignment.source_id, "content_version": graph.content_version}
                    for c in graph.concepts.values()]
        edges = {relation: [] for relation in RELATIONS}
        for e in graph.edges:
            edges[e.relation].append({
                "source": e.source_concept_id, "target": e.target_concept_id,
                "props": {"edge_id": e.edge_id, "rationale": e.rationale, "source_id": e.source_id,
                          "review_status": e.review.status, "effective_status": graph.status(e.edge_id),
                          "human_reviewer": e.review.human_reviewer, "reviewed_at": e.review.reviewed_at}})
        meta = {"content_version": graph.content_version, "fingerprint": graph.fingerprint,
                "concepts": len(concepts), "edges": len(graph.edges),
                "synced_at": datetime.now(timezone.utc).isoformat()}

        def write(tx):
            tx.run("UNWIND $rows AS row MERGE (c:Concept {concept_id: row.concept_id}) SET c = row", rows=concepts)
            tx.run("MATCH (c:Concept) WHERE NOT c.concept_id IN $ids DETACH DELETE c",
                   ids=[c["concept_id"] for c in concepts])
            tx.run("MATCH (:Concept)-[r:PREREQUISITE_OF|RELATED_TO|PART_OF]->(:Concept) DELETE r")
            for relation, rows in edges.items():  # tên quan hệ lấy từ RELATIONS cố định, không từ dữ liệu
                tx.run("UNWIND $rows AS row "
                       "MATCH (a:Concept {concept_id: row.source}), (b:Concept {concept_id: row.target}) "
                       f"CREATE (a)-[r:{relation}]->(b) SET r = row.props", rows=rows)
            tx.run("MERGE (m:KGMeta {id: 'registry'}) SET m += $meta", meta=meta)

        with self._session() as session:
            session.run("CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) "
                        "REQUIRE c.concept_id IS UNIQUE").consume()
            session.run("CREATE CONSTRAINT kg_meta_id IF NOT EXISTS FOR (m:KGMeta) REQUIRE m.id IS UNIQUE").consume()
            session.execute_write(write)
        return meta

    # ----------------------------------------------------------------------- truy vấn

    def meta(self) -> dict | None:
        record = self._read(
            lambda tx: tx.run("MATCH (m:KGMeta {id: 'registry'}) RETURN properties(m) AS meta").single())
        return dict(record["meta"]) if record else None

    def neighbourhood(self, concept_id: str, *, include_drafts: bool = False,
                      max_depth: int = MAX_DEPTH) -> Neighbourhood:
        if max_depth not in (1, 2):
            raise ValueError("Chỉ hỗ trợ truy 1 hoặc 2 tầng prerequisite")

        def read(tx):
            params = {"id": concept_id, "drafts": include_drafts}
            head = tx.run(_META, **params).single()
            if head is None:
                raise GraphNotSynced("Neo4j chưa có KGMeta; chạy scripts/dev/sync_kg_neo4j.py")
            if not head["known"]:
                raise UnknownConcept(concept_id)
            rows = [(1, r.data()) for r in tx.run(_DEPTH_1, **params)]
            if max_depth == 2:
                rows += [(2, r.data()) for r in tx.run(_DEPTH_2, **params)]
            return head.data(), rows, [r.data() for r in tx.run(_SUCCESSORS, **params)]

        head, rows, successors = self._read(read)
        prerequisites = sorted((PrerequisiteEdge(r["edge_id"], r["source"], r["target"], tuple(r["skills"]),
                                                 depth, r["status"]) for depth, r in rows),
                               key=lambda e: (e.depth, e.edge_id))
        next_concepts = sorted((NextConcept(r["concept_id"], tuple(r["skills"]), r["edge_id"], r["status"],
                                            tuple(sk for skills in r["other"] for sk in skills))
                                for r in successors), key=lambda n: n.edge_id)
        return Neighbourhood(tuple(prerequisites), tuple(next_concepts), head["content_version"],
                             head["fingerprint"])

    def prerequisites(self, concept_id: str, max_depth: int = MAX_DEPTH, *,
                      include_drafts: bool = False) -> list[PrerequisiteEdge]:
        return list(self.neighbourhood(concept_id, include_drafts=include_drafts, max_depth=max_depth).prerequisites)

    def successors(self, concept_id: str, *, include_drafts: bool = False) -> list[NextConcept]:
        return list(self.neighbourhood(concept_id, include_drafts=include_drafts).next_concepts)
