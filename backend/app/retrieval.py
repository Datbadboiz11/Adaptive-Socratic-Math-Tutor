"""Scoped exact retrieval. Inference is outside DB transactions; retrieval is not delivery."""
from time import perf_counter
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db import connect
from app.embeddings import checked_vector, vector_literal
from app.kb_contracts import EmbeddingProfile, KBChunk, KBRequest, KBResult, KB_VERSION, validate_result
from app.manage import digest


class KBRetriever:
    def __init__(self, embedder=None, connection_factory=connect):
        self.embedder = embedder
        self.connection_factory = connection_factory

    def _snapshot(self, c, request):
        row = c.execute("""SELECT s.*,p.configuration,r.payload AS registry_payload,r.registry_hash,
            (SELECT count(*) FROM kb_snapshot_members m WHERE m.namespace=s.namespace AND m.snapshot_id=s.snapshot_id) AS member_count
            FROM kb_snapshots s JOIN kb_embedding_profiles p USING(profile_id)
            JOIN kb_registry_versions r ON r.namespace=s.namespace AND r.registry_version=s.registry_version
            WHERE s.namespace=%s AND s.snapshot_id=%s""",
            (request.scope.namespace, request.scope.kb_snapshot_version)).fetchone()
        if not row:
            return None
        profile = EmbeddingProfile.model_validate(row["configuration"])
        if (digest(row["manifest"]) != row["manifest_hash"] or row["snapshot_id"] != "KB-"+row["manifest_hash"]
                or row["manifest"]["namespace"] != request.scope.namespace
                or row["manifest"]["profile_id"] != row["profile_id"]
                or row["member_count"] != row["chunk_count"] or row["chunk_count"] != len(row["manifest"]["chunks"])
                or profile.profile_id != row["profile_id"]
                or digest(row["registry_payload"]) != row["registry_hash"]
                or row["manifest"]["registry_hash"] != row["registry_hash"]):
            raise ValueError("Snapshot/model/registry integrity failed")
        if request.scope.namespace == "runtime" and (row["manifest"]["synthetic_fixture"] or profile.provider == "synthetic_fixture"):
            raise ValueError("Fixture snapshot cannot serve runtime content")
        valid = {(co["concept_id"], sk["skill_id"]) for co in row["registry_payload"]["concepts"] for sk in co["skills"]}
        if any((t.concept_id, t.skill_id) not in valid for t in request.scope.allowed_targets):
            raise ValueError("Server scope references a pair outside this snapshot")
        return row

    @staticmethod
    def _filters(request):
        scope, query = request.scope, request.query
        where = """ FROM kb_snapshot_members m
            JOIN kb_chunks ch USING(namespace,content_id,content_version,text_hash)
            JOIN kb_concepts co ON co.namespace=ch.namespace AND co.registry_version=ch.registry_version AND co.concept_id=ch.concept_id
            JOIN kb_embeddings e ON e.profile_id=m.profile_id AND e.text_hash=m.text_hash
            WHERE m.namespace=%s AND m.snapshot_id=%s
            AND ch.concept_id=%s AND %s=ANY(ch.skill_ids) AND ch.kind=%s AND ch.hint_level<=%s
            AND ch.grade_levels && %s::integer[] AND (ch.difficulty IS NULL OR ch.difficulty=%s)
            AND co.payload->'review'->>'status'='human_approved'
            AND co.payload->'alignment'->>'status'='human_approved'
            AND ch.payload->'review'->>'status'='human_approved'
            AND ch.payload->'counts_as_assistance'='true'::jsonb
            AND (ch.problem_id IS NULL OR ch.problem_id IS DISTINCT FROM %s)
            AND (ch.source_group IS NULL OR NOT(ch.source_group=ANY(%s::text[])))
            AND (ch.kind<>'example' OR (NOT(ch.family_id=ANY(%s::text[])) AND NOT(ch.lineage_ids && %s::text[])))
            AND ((ch.kind='explanation' AND ch.hint_level=0 AND ch.disclosure='conceptual')
                OR (ch.kind='hint' AND ((ch.hint_level=1 AND ch.disclosure='conceptual')
                    OR (ch.hint_level=2 AND ch.disclosure='strategy') OR (ch.hint_level=3 AND ch.disclosure='scaffold')))
                OR (ch.kind='example' AND ch.hint_level=3 AND ch.disclosure='different_example'))
            AND NOT EXISTS (SELECT 1 FROM kb_withdrawals w WHERE w.namespace=ch.namespace
                            AND w.concept_id=ch.concept_id AND w.pack_version=ch.pack_version)"""
        parameters = [scope.namespace,scope.kb_snapshot_version,query.concept_id,query.target_skill_id,query.purpose,
            scope.allowed_hint_level,scope.grade_levels,scope.difficulty,scope.active_problem_id,
            scope.excluded_source_groups,scope.excluded_family_ids,scope.excluded_lineage_ids]
        if request.direct_ref:
            where += " AND ch.content_id=%s AND ch.content_version=%s"
            parameters.extend([request.direct_ref.content_id,request.direct_ref.content_version])
        return where, parameters

    def retrieve(self, request: KBRequest):
        request = KBRequest.model_validate(request.model_dump(mode="json"))
        started = perf_counter()
        retrieval_id = uuid4()
        snapshot = None
        rows, error_class = [], None
        eligible_count = 0
        reason = "retrieval_unavailable"
        try:
            where, params = self._filters(request)
            with self.connection_factory() as c:
                # Bound the read without changing caller/global transaction settings.
                c.execute("SET LOCAL statement_timeout='2500ms'")
                snapshot = self._snapshot(c, request)
                if snapshot and request.method == "semantic":
                    eligible_count = c.execute("SELECT count(*) AS n" + where, params).fetchone()["n"]
                elif snapshot:
                    rows = c.execute("SELECT ch.payload,ch.content_hash,NULL::double precision AS distance,count(*) OVER() AS candidate_count" + where
                        + " ORDER BY ch.content_id,ch.content_version LIMIT %s", [*params,request.query.top_k]).fetchall()
                    eligible_count = rows[0]["candidate_count"] if rows else 0
            reason = "snapshot_unavailable" if not snapshot else "no_eligible_content"
            if snapshot and eligible_count and request.method == "semantic":
                if not self.embedder or self.embedder.profile.profile_id != snapshot["profile_id"]:
                    raise ValueError("Query embedding profile differs from snapshot")
                vector = checked_vector(self.embedder.embed_query(request.query.query), self.embedder.profile.dimension)
                # No database connection is open during embed_query(). Reapply every filter after inference.
                with self.connection_factory() as c:
                    c.execute("SET LOCAL statement_timeout='2500ms'")
                    fresh = self._snapshot(c, request)
                    if not fresh or fresh["manifest_hash"] != snapshot["manifest_hash"]:
                        raise ValueError("Snapshot changed during inference")
                    rows = c.execute("""SELECT ch.payload,ch.content_hash,
                        e.embedding OPERATOR(public.<=>) %s::public.vector AS distance,
                        count(*) OVER() AS candidate_count""" + where
                        + " ORDER BY distance,ch.content_id,ch.content_version LIMIT %s",
                        [vector_literal(vector),*params,request.query.top_k]).fetchall()
                    eligible_count = rows[0]["candidate_count"] if rows else 0
            chunks = []
            for row in rows:
                if digest(row["payload"]) != row["content_hash"]:
                    raise ValueError("Retrieved payload hash mismatch")
                chunks.append(KBChunk.model_validate(row["payload"]))
            result = KBResult(retrieval_id=retrieval_id,request_id=request.request_id,
                kb_snapshot_version=request.scope.kb_snapshot_version,
                snapshot_manifest_hash=snapshot["manifest_hash"] if snapshot else None,
                registry_version=snapshot["registry_version"] if snapshot else None,
                embedding_version=snapshot["profile_id"] if snapshot else None, method=request.method,
                elapsed_ms=(perf_counter()-started)*1000, eligible_count=eligible_count, chunks=chunks,
                fallback_reason=None if chunks else reason)
            validate_result(request, result)
        except Exception as error:
            error_class = type(error).__name__
            rows = []
            result = KBResult(retrieval_id=retrieval_id,request_id=request.request_id,
                kb_snapshot_version=request.scope.kb_snapshot_version,method=request.method,
                elapsed_ms=(perf_counter()-started)*1000,eligible_count=0,chunks=[],fallback_reason="retrieval_unavailable")
        try:
            # Trace retrieval only. Member 3 must separately record context injection and delivery in Chặng 4.
            selected = [{"content_id": ch.content_id,"content_version": ch.content_version,"content_hash": ch.content_hash,
                         "cosine_distance": row["distance"]} for ch,row in zip(result.chunks,rows)]
            with self.connection_factory() as c:
                c.execute("""INSERT INTO kb_retrieval_traces
                    (retrieval_id,request_id,namespace,snapshot_id,query_hash,scope_hash,config_version,method,
                     embedding_profile_id,elapsed_ms,selected_refs,fallback_reason,error_class)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (result.retrieval_id,request.request_id,request.scope.namespace,request.scope.kb_snapshot_version,
                     digest(request.query.model_dump(mode="json")),digest(request.scope.model_dump(mode="json")),KB_VERSION,
                     request.method,result.embedding_version,result.elapsed_ms,Jsonb(selected),result.fallback_reason,error_class))
        except Exception:
            # Do not return untraceable teaching content when audit persistence fails.
            return KBResult(retrieval_id=retrieval_id,request_id=request.request_id,
                kb_snapshot_version=request.scope.kb_snapshot_version,method=request.method,
                elapsed_ms=(perf_counter()-started)*1000,eligible_count=0,chunks=[],fallback_reason="retrieval_unavailable")
        return result
