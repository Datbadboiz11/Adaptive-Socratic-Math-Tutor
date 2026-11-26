"""Transactional KB publication. No model call, download or private-reference persistence."""
from dataclasses import replace
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db import connect
from app.embeddings import checked_vector, vector_hash, vector_literal
from app.kb_contracts import EmbeddingProfile
from app.kb_projection import Projection
from app.manage import digest


class KBConflict(ValueError):
    """Controlled conflict messages contain no source text or credentials."""


def active_snapshot(connection, namespace="runtime"):
    row = connection.execute("SELECT snapshot_id FROM kb_channels WHERE namespace=%s", (namespace,)).fetchone()
    return row["snapshot_id"] if row else None


def namespace_lock(connection, namespace):
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("kb:" + namespace,))


def effective_projection(connection, projection):
    withdrawn = {(r["concept_id"], r["pack_version"]) for r in connection.execute(
        "SELECT concept_id,pack_version FROM kb_withdrawals WHERE namespace=%s", (projection.namespace,)).fetchall()}
    chunks = tuple(c for c in projection.chunks if (c.concept_id, c.provenance.pack_version) not in withdrawn)
    blocked = projection.blocked + tuple({"concept_id": c.concept_id, "content_id": c.content_id,
        "reasons": ["withdrawn_pack_version"]} for c in projection.chunks if c not in chunks)
    return replace(projection, chunks=chunks, blocked=blocked)


def _immutable_check(connection, projection):
    old = connection.execute("SELECT registry_hash FROM kb_registry_versions WHERE namespace=%s AND registry_version=%s",
                             (projection.namespace, projection.registry.content_version)).fetchone()
    if old and old["registry_hash"] != projection.registry_hash:
        raise KBConflict("Registry version changed; create a new version")
    for chunk in projection.chunks:
        old = connection.execute("SELECT content_hash FROM kb_chunks WHERE namespace=%s AND content_id=%s AND content_version=%s",
                                 (projection.namespace, chunk.content_id, chunk.content_version)).fetchone()
        if old and old["content_hash"] != chunk.content_hash:
            raise KBConflict("Chunk version changed; create a new version")


def plan_sync(projection: Projection, connection_factory=connect):
    projection.validate()
    with connection_factory() as c:
        if not c.execute("SELECT to_regclass('kb_snapshots') AS name").fetchone()["name"]:
            raise KBConflict("KB migration is required before planning or synchronizing")
        projection = effective_projection(c, projection)
        _immutable_check(c, projection)
        hashes = sorted({chunk.text_hash for chunk in projection.chunks})
        cached = {r["text_hash"] for r in c.execute("SELECT text_hash FROM kb_embeddings WHERE profile_id=%s AND text_hash=ANY(%s::text[])",
                                                   (projection.profile.profile_id, hashes)).fetchall()}
        existing = {(r["content_id"], r["content_version"]) for r in c.execute(
            "SELECT content_id,content_version FROM kb_chunks WHERE namespace=%s", (projection.namespace,)).fetchall()}
        snapshot = c.execute("SELECT manifest_hash FROM kb_snapshots WHERE namespace=%s AND snapshot_id=%s",
                             (projection.namespace, projection.snapshot_id)).fetchone()
        current = active_snapshot(c, projection.namespace)
    summary = {"namespace": projection.namespace, "snapshot_id": projection.snapshot_id,
        "synthetic_fixture": projection.namespace != "runtime", "registry_version": projection.registry.content_version,
        "registry_hash": projection.registry_hash, "bank_hash": projection.bank_hash,
        "profile_id": projection.profile.profile_id, "dimension": projection.profile.dimension,
        "concepts": len(projection.registry.concepts), "skills": sum(len(c.skills) for c in projection.registry.concepts),
        "chunks": len(projection.chunks), "blocked": list(projection.blocked),
        "new_chunk_versions": sum((c.content_id, c.content_version) not in existing for c in projection.chunks),
        "new_embeddings": len(set(hashes) - cached), "cached_embeddings": len(cached),
        "snapshot_exists": bool(snapshot), "active_snapshot_before": current,
        "source_files_modified": False, "model_api_calls": 0}
    return projection, summary


def _write_registry(c, p):
    version = p.registry.content_version
    if c.execute("SELECT 1 FROM kb_registry_versions WHERE namespace=%s AND registry_version=%s", (p.namespace, version)).fetchone():
        return
    c.execute("INSERT INTO kb_registry_versions VALUES (%s,%s,%s,%s)",
              (p.namespace, version, p.registry_hash, Jsonb(p.registry.model_dump(mode="json"))))
    for concept in p.registry.concepts:
        c.execute("INSERT INTO kb_concepts VALUES (%s,%s,%s,%s)",
                  (p.namespace, version, concept.concept_id, Jsonb(concept.model_dump(mode="json"))))
        for skill in concept.skills:
            c.execute("INSERT INTO kb_skills VALUES (%s,%s,%s,%s,%s)",
                      (p.namespace, version, concept.concept_id, skill.skill_id, Jsonb(skill.model_dump(mode="json"))))
    for mapping in p.registry.legacy_mappings:
        c.execute("INSERT INTO kb_legacy_mappings VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                  (p.namespace, version, mapping.legacy_concept_id, mapping.legacy_skill_id, mapping.concept_id,
                   mapping.skill_id, mapping.status, Jsonb(mapping.model_dump(mode="json"))))


def assert_complete(c, namespace, snapshot_id):
    snapshot = c.execute("SELECT * FROM kb_snapshots WHERE namespace=%s AND snapshot_id=%s", (namespace, snapshot_id)).fetchone()
    if (not snapshot or digest(snapshot["manifest"]) != snapshot["manifest_hash"]
            or snapshot_id != "KB-" + snapshot["manifest_hash"]
            or snapshot["manifest"]["namespace"] != namespace
            or snapshot["manifest"]["profile_id"] != snapshot["profile_id"]):
        raise KBConflict("Snapshot is missing or manifest integrity failed")
    profile_row = c.execute("SELECT * FROM kb_embedding_profiles WHERE profile_id=%s", (snapshot["profile_id"],)).fetchone()
    profile = EmbeddingProfile.model_validate(profile_row["configuration"])
    registry = c.execute("SELECT payload,registry_hash FROM kb_registry_versions WHERE namespace=%s AND registry_version=%s",
                         (namespace,snapshot["registry_version"])).fetchone()
    if (profile.profile_id != snapshot["profile_id"] or profile.dimension != profile_row["dimension"]
            or digest(registry["payload"]) != registry["registry_hash"]
            or registry["registry_hash"] != snapshot["manifest"]["registry_hash"]):
        raise KBConflict("Snapshot profile/registry integrity failed")
    rows = c.execute("""SELECT ch.content_id,ch.content_version,ch.content_hash,ch.text_hash,ch.concept_id,ch.pack_version,
        ch.payload,e.profile_id,e.dimension,e.embedding,e.vector_hash
        FROM kb_snapshot_members m JOIN kb_chunks ch USING(namespace,content_id,content_version,text_hash)
        JOIN kb_embeddings e ON e.profile_id=m.profile_id AND e.text_hash=m.text_hash
        WHERE m.namespace=%s AND m.snapshot_id=%s ORDER BY ch.content_id,ch.content_version""", (namespace, snapshot_id)).fetchall()
    actual = [{key: row[key] for key in ("content_id", "content_version", "content_hash", "text_hash")} for row in rows]
    if len(rows) != snapshot["chunk_count"] or actual != snapshot["manifest"]["chunks"]:
        raise KBConflict("Snapshot membership or embeddings are incomplete")
    if any(digest(row["payload"]) != row["content_hash"] or row["profile_id"] != snapshot["profile_id"] for row in rows):
        raise KBConflict("Snapshot payload or embedding profile integrity failed")
    if any(row["dimension"] != profile.dimension or vector_hash(json.loads(row["embedding"])) != row["vector_hash"] for row in rows):
        raise KBConflict("Snapshot embedding integrity failed")
    if c.execute("""SELECT 1 FROM kb_snapshot_members m JOIN kb_chunks ch USING(namespace,content_id,content_version)
        JOIN kb_withdrawals w ON w.namespace=ch.namespace AND w.concept_id=ch.concept_id AND w.pack_version=ch.pack_version
        WHERE m.namespace=%s AND m.snapshot_id=%s LIMIT 1""", (namespace, snapshot_id)).fetchone():
        raise KBConflict("Snapshot includes withdrawn content; synchronize a new snapshot")
    if namespace == "runtime":
        profile = c.execute("SELECT provider FROM kb_embedding_profiles WHERE profile_id=%s", (snapshot["profile_id"],)).fetchone()
        if snapshot["manifest"]["synthetic_fixture"] or profile["provider"] == "synthetic_fixture":
            raise KBConflict("Synthetic fixtures cannot activate the runtime channel")
    return snapshot


def _activate(c, namespace, snapshot_id, expected_active):
    assert_complete(c, namespace, snapshot_id)
    current = active_snapshot(c, namespace)
    if current not in (expected_active, snapshot_id):
        raise KBConflict("Active snapshot changed during preparation; replan before activation")
    c.execute("""INSERT INTO kb_channels(namespace,snapshot_id) VALUES (%s,%s)
        ON CONFLICT(namespace) DO UPDATE SET snapshot_id=EXCLUDED.snapshot_id,activated_at=now()""", (namespace, snapshot_id))


def activate_snapshot(namespace, snapshot_id, connection_factory=connect):
    with connection_factory() as c:
        namespace_lock(c, namespace)
        previous = active_snapshot(c, namespace)
        _activate(c, namespace, snapshot_id, previous)
    return {"namespace": namespace, "previous_snapshot": previous, "active_snapshot": snapshot_id}


def sync_projection(projection, embedder, *, activate=False, connection_factory=connect):
    p, summary = plan_sync(projection, connection_factory)
    if embedder.profile.profile_id != p.profile.profile_id:
        raise ValueError("Embedding provider/profile mismatch")
    run_id = uuid4()
    with connection_factory() as c:
        c.execute("INSERT INTO kb_sync_runs(run_id,namespace,snapshot_id,status,summary) VALUES (%s,%s,%s,'preparing',%s)",
                  (run_id, p.namespace, p.snapshot_id, Jsonb(summary)))
        cached = {r["text_hash"] for r in c.execute("SELECT text_hash FROM kb_embeddings WHERE profile_id=%s", (p.profile.profile_id,)).fetchall()}
    try:
        pending = {ch.text_hash: ch.text for ch in p.chunks if ch.text_hash not in cached}
        texts = list(pending.values())
        # No open database transaction while loading weights or calculating embeddings.
        raw = embedder.embed_many(texts) if texts else []
        if len(raw) != len(texts):
            raise ValueError("Incomplete embedding batch")
        vectors = {text_hash: checked_vector(v, p.profile.dimension) for text_hash, v in zip(pending, raw)}
        with connection_factory() as c:
            namespace_lock(c, p.namespace)
            p.validate()
            _immutable_check(c, p)
            if len(effective_projection(c, p).chunks) != len(p.chunks):
                raise KBConflict("Content was withdrawn during preparation; replan")
            _write_registry(c, p)
            c.execute("""INSERT INTO kb_embedding_profiles VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                      (p.profile.profile_id, p.profile.dimension, p.profile.provider, Jsonb(p.profile.model_dump(mode="json"))))
            for text_hash, vector in vectors.items():
                c.execute("""INSERT INTO kb_embeddings VALUES (%s,%s,%s,%s::public.vector,%s) ON CONFLICT DO NOTHING""",
                          (p.profile.profile_id, text_hash, p.profile.dimension, vector_literal(vector), vector_hash(vector)))
            inserted_chunks = 0
            for ch in p.chunks:
                result = c.execute("""INSERT INTO kb_chunks VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (p.namespace,ch.content_id,ch.content_version,p.registry.content_version,ch.concept_id,ch.provenance.pack_version,
                     ch.content_hash,ch.text_hash,ch.text,Jsonb(ch.model_dump(mode="json")),ch.skill_ids,ch.kind,ch.hint_level,
                     ch.disclosure,ch.grade_levels,ch.difficulty,ch.problem_id,ch.source_group,ch.family_id,ch.lineage_ids))
                inserted_chunks += result.rowcount
            c.execute("INSERT INTO kb_snapshots VALUES (%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT DO NOTHING",
                      (p.namespace,p.snapshot_id,p.registry.content_version,p.profile.profile_id,digest(p.manifest),Jsonb(p.manifest),len(p.chunks)))
            for ch in p.chunks:
                c.execute("INSERT INTO kb_snapshot_members VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                          (p.namespace,p.snapshot_id,ch.content_id,ch.content_version,p.profile.profile_id,ch.text_hash))
            assert_complete(c, p.namespace, p.snapshot_id)
            if activate:
                _activate(c, p.namespace, p.snapshot_id, summary["active_snapshot_before"])
            completed = {**summary, "run_id": str(run_id), "status": "published", "inserted_chunks": inserted_chunks,
                         "computed_embeddings": len(vectors), "activated": activate}
            c.execute("UPDATE kb_sync_runs SET status='published',finished_at=now(),summary=%s WHERE run_id=%s",
                      (Jsonb(completed),run_id))
        return completed
    except Exception as error:
        with connection_factory() as c:
            c.execute("UPDATE kb_sync_runs SET status='failed',finished_at=now(),error_class=%s WHERE run_id=%s",
                      (type(error).__name__,run_id))
        raise


def withdraw_pack(namespace, concept_id, pack_version, reason, actor, connection_factory=connect):
    if not reason.strip() or not actor.strip():
        raise ValueError("Withdrawal requires a reason and actor")
    with connection_factory() as c:
        namespace_lock(c, namespace)
        result = c.execute("INSERT INTO kb_withdrawals(namespace,concept_id,pack_version,reason,actor) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                           (namespace,concept_id,pack_version,reason.strip(),actor.strip()))
    return {"namespace": namespace, "concept_id": concept_id, "pack_version": pack_version, "new_withdrawal": bool(result.rowcount)}
