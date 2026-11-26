"""Exact vector retrieval for authoring research only; no production publication path."""
import json
import hashlib
import math
import re

from psycopg import sql
from psycopg.types.json import Jsonb

DIMENSION = 384


def checksum(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def vector_literal(values):
    values = [float(value) for value in values]
    if len(values) != DIMENSION or not all(math.isfinite(value) for value in values) or not any(values):
        raise ValueError("Expected a finite, nonzero 384-dimensional vector")
    return json.dumps(values, separators=(",", ":"))


class DevVectorStore:
    def __init__(self, connection, schema="member2_retrieval_dev"):
        if not re.fullmatch(r"(?:member2_retrieval_dev|test_retrieval_[a-f0-9]{32})", schema):
            raise ValueError("Research store must use a dedicated schema")
        self.connection = connection
        self.schema = sql.Identifier(schema)

    def execute(self, query, args=None):
        return self.connection.execute(sql.SQL(query).format(schema=self.schema), args)

    def initialize(self):
        self.execute("CREATE SCHEMA IF NOT EXISTS {schema}")
        self.execute("""CREATE TABLE IF NOT EXISTS {schema}.snapshots (
            snapshot_id text NOT NULL, model_id text NOT NULL, corpus_hash text NOT NULL,
            usage text NOT NULL CHECK (usage='authoring_dev_only_not_runtime'),
            PRIMARY KEY(snapshot_id,model_id))""")
        self.execute("""CREATE TABLE IF NOT EXISTS {schema}.chunks (
            snapshot_id text NOT NULL, model_id text NOT NULL, content_id text NOT NULL,
            content_hash text NOT NULL, concept_id text NOT NULL, skill_ids text[] NOT NULL,
            kind text NOT NULL CHECK(kind IN ('explanation','hint')), hint_level integer NOT NULL,
            grade_levels integer[] NOT NULL, problem_id text, source_group text,
            disclosure text NOT NULL, payload jsonb NOT NULL, embedding public.vector(384) NOT NULL,
            PRIMARY KEY(snapshot_id,model_id,content_id),
            FOREIGN KEY(snapshot_id,model_id) REFERENCES {schema}.snapshots(snapshot_id,model_id))""")

    def sync(self, corpus, corpus_hash, model_id, embeddings):
        if corpus.get("usage") != "authoring_dev_only_not_runtime":
            raise ValueError("This store accepts authoring research snapshots only")
        if checksum(corpus) != corpus_hash:
            raise ValueError("Corpus checksum mismatch")
        docs = corpus["documents"]
        if not docs or len({doc["content_id"] for doc in docs}) != len(docs):
            raise ValueError("Empty or duplicate corpus")
        if any(doc["runtime_eligible"] or doc["review_status"] != "draft"
               or doc["kind"] not in ("explanation", "hint") for doc in docs):
            raise ValueError("This dev fixture must stay explicitly draft and non-runtime")
        if any(checksum({k: v for k, v in doc.items() if k != "content_sha256"}) != doc["content_sha256"] for doc in docs):
            raise ValueError("Document checksum mismatch")
        vectors = [vector_literal(embeddings[doc["content_id"]]) for doc in docs]
        # Caller owns the outer transaction. Savepoint makes a failed sync all-or-nothing.
        with self.connection.transaction():
            self.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("member2-dev-sync",))
            old = self.execute("SELECT corpus_hash FROM {schema}.snapshots WHERE snapshot_id=%s AND model_id=%s",
                               (corpus["snapshot_id"], model_id)).fetchone()
            if old:
                if old["corpus_hash"] != corpus_hash:
                    raise ValueError("Snapshot is immutable; create a new ID")
                count = self.execute("SELECT count(*) AS n FROM {schema}.chunks WHERE snapshot_id=%s AND model_id=%s",
                                     (corpus["snapshot_id"], model_id)).fetchone()["n"]
                if count != len(docs):
                    raise ValueError("Incomplete existing snapshot")
                return {"inserted": 0, "total": count}
            self.execute("INSERT INTO {schema}.snapshots VALUES (%s,%s,%s,%s)",
                         (corpus["snapshot_id"], model_id, corpus_hash, corpus["usage"]))
            for doc, vector in zip(docs, vectors):
                self.execute("""INSERT INTO {schema}.chunks VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::public.vector)""",
                    (corpus["snapshot_id"], model_id, doc["content_id"], doc["content_sha256"], doc["concept_id"],
                     doc["skill_ids"], doc["kind"], doc["hint_level"], doc["grade_levels"], doc["problem_id"],
                     doc["source_group"], doc["disclosure"], Jsonb(doc), vector))
        return {"inserted": len(docs), "total": len(docs)}

    def retrieve(self, snapshot_id, model_id, query, embedding, semantic=True, top_k=5):
        if not 1 <= top_k <= 20:
            raise ValueError("Invalid result limit")
        vector = vector_literal(embedding)
        # Metadata authority comes from the pinned dev fixture. This is deliberately not a public API.
        return self.execute("""SELECT content_id,
            embedding OPERATOR(public.<=>) %s::public.vector AS distance
            FROM {schema}.chunks WHERE snapshot_id=%s AND model_id=%s
            AND concept_id=%s AND %s=ANY(skill_ids) AND kind=%s AND hint_level<=%s
            AND grade_levels && %s::integer[]
            AND (problem_id IS NULL OR problem_id IS DISTINCT FROM %s)
            AND (source_group IS NULL OR NOT(source_group=ANY(%s::text[])))
            AND disclosure=ANY(%s::text[])
            ORDER BY CASE WHEN %s THEN embedding OPERATOR(public.<=>) %s::public.vector END ASC,
                     content_id ASC LIMIT %s""",
            (vector, snapshot_id, model_id, query["concept_id"], query["target_skill_id"], query["purpose"],
             query["allowed_hint_level"], query["grade_levels"], query["active_problem_id"],
             query["excluded_source_groups"], ["conceptual", "strategy", "scaffold"], semantic, vector, top_k)).fetchall()
