"""Metric edge cases and actual pgvector filtering/snapshot rollback, using synthetic vectors."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from research.retrieval.metrics import aggregate, score
from research.retrieval.pgvector_dev import DevVectorStore, checksum, vector_literal


def test_member2_benchmark_covers_every_published_concept_and_chunk():
    base = ROOT / "research/retrieval/dev/member2-13.v1"
    corpus = json.loads((base / "corpus.json").read_text(encoding="utf-8"))
    queries = json.loads((base / "queries.json").read_text(encoding="utf-8"))
    qrels = json.loads((base / "qrels.json").read_text(encoding="utf-8"))
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    concepts = set(manifest["concept_ids"])
    assert len(concepts)==manifest["concept_count"]==13
    assert len(corpus["documents"])==manifest["document_count"]==91
    assert len(queries)==manifest["query_count"]==104
    assert len(qrels)==manifest["judgment_count"]==169
    assert {doc["concept_id"] for doc in corpus["documents"]}==concepts
    assert {query["concept_id"] for query in queries}==concepts
    assert all(sum(query["query_id"].startswith(f"M2-{concept}-") for query in queries)==8 for concept in concepts)
    assert sum(not query["eligible_candidate_ids"] for query in queries)==13
    valid = {(query["query_id"],content_id) for query in queries for content_id in query["eligible_candidate_ids"]}
    assert {(row["query_id"],row["content_id"]) for row in qrels}==valid


def test_partial_only_query_has_ndcg_but_no_recall_or_hit():
    result = score(["partial"], {"partial": 1, "irrelevant": 0}, 1)
    assert result == {"recall": None, "hit": None, "ndcg": 1.0}
    assert score([], {"none": 0}, 3) == {"recall": None, "hit": None, "ndcg": None}
    assert aggregate([result, score([], {"none": 0}, 3)])["ndcg"] == {
        "mean": 1.0, "defined_queries": 1, "undefined_queries": 1}


def test_metrics_use_all_relevant_documents_as_denominator():
    result = score(["partial", "good"], {"partial": 1, "good": 2, "missing": 2}, 1)
    assert result["recall"] == result["hit"] == 0 and result["ndcg"] == pytest.approx(1 / 3)
    assert score(["good"], {"good": 2, "missing": 2}, 5)["recall"] == 0.5
    assert score(["good", "partial"], {"good": 2, "partial": 1}, 2)["ndcg"] == 1


@pytest.mark.parametrize("ranking,grades", [(["a", "a"], {"a": 2}), (["unknown"], {"a": 2}), (["a"], {"a": True})])
def test_metrics_reject_invalid_runs(ranking, grades):
    with pytest.raises(ValueError):
        score(ranking, grades, 1)


@pytest.mark.parametrize("values", [[1.0] * 383, [0.0] * 384, [math.nan] * 384, [math.inf] * 384])
def test_vector_validation(values):
    with pytest.raises(ValueError):
        vector_literal(values)


@pytest.fixture
def store():
    if not os.getenv("RUN_DB_TESTS"):
        pytest.skip("Real pgvector requires RUN_DB_TESTS=1")
    from app.db import connect
    with connect() as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    with connect() as c:
        fixture = DevVectorStore(c, "test_retrieval_" + uuid4().hex)
        fixture.initialize()
        yield fixture
        # Roll back only the new synthetic schema and rows from this test.
        c.rollback()


@pytest.fixture
def data():
    from app.curriculum import load_curriculum
    from app.retrieval_dev import candidate_corpus
    registry, bank = load_curriculum()
    prepared = {pack.concept_id: {"draft.json": pack.model_dump(mode="json"),
                 "request.json": {"revision": "SYNTHETIC"}} for pack in bank.packs
                if pack.concept_id in ("A02", "E02")}
    corpus = candidate_corpus(prepared, registry, "SYNTHETIC-RETRIEVAL-ONLY")
    queries = [{"concept_id": doc["concept_id"], "target_skill_id": doc["skill_ids"][0],
                "purpose": "explanation", "allowed_hint_level": 0, "grade_levels": doc["grade_levels"],
                "active_problem_id": "SYNTHETIC-ACTIVE", "excluded_source_groups": []}
               for doc in corpus["documents"] if doc["kind"] == "explanation"]
    vectors = {doc["content_id"]: [1.0] + [0.0] * 383 for doc in corpus["documents"]}
    return corpus, queries, vectors


def test_real_sync_idempotency_hash_lock_and_metadata_filters(store, data):
    from app.retrieval_dev import blocking_reasons
    corpus, queries, vectors = data
    assert store.sync(corpus, checksum(corpus), "synthetic", vectors) == {"inserted": 8, "total": 8}
    assert store.sync(corpus, checksum(corpus), "synthetic", vectors) == {"inserted": 0, "total": 8}
    for query in queries:
        result = store.retrieve(corpus["snapshot_id"], "synthetic", query, next(iter(vectors.values())), top_k=8)
        assert sorted(row["content_id"] for row in result) == sorted(
            doc["content_id"] for doc in corpus["documents"] if not blocking_reasons(doc, query))
    changed = deepcopy(corpus)
    changed["documents"][0]["text"] += " Changed."
    doc = changed["documents"][0]
    doc["content_sha256"] = checksum({k: v for k, v in doc.items() if k != "content_sha256"})
    with pytest.raises(ValueError, match="immutable"):
        store.sync(changed, checksum(changed), "synthetic", vectors)
    assert len(store.retrieve(corpus["snapshot_id"], "synthetic", queries[0], next(iter(vectors.values())))) == 1


def test_failed_sync_rolls_back_snapshot_and_chunks(store, data):
    corpus, _, vectors = data
    corpus["documents"][1]["hint_level"] = "not-an-integer"
    doc = corpus["documents"][1]
    doc["content_sha256"] = checksum({k: v for k, v in doc.items() if k != "content_sha256"})
    import psycopg
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        store.sync(corpus, checksum(corpus), "synthetic", vectors)
    assert store.execute("SELECT count(*) AS n FROM {schema}.snapshots").fetchone()["n"] == 0
    assert store.execute("SELECT count(*) AS n FROM {schema}.chunks").fetchone()["n"] == 0


def test_unknown_model_and_concept_skill_pair_return_no_content(store, data):
    corpus, queries, vectors = data
    store.sync(corpus, checksum(corpus), "synthetic", vectors)
    vector = next(iter(vectors.values()))
    assert store.retrieve(corpus["snapshot_id"], "unknown-model", queries[0], vector) == []
    query = {**queries[0], "target_skill_id": "SK-E02-SOLVE"}
    assert store.retrieve(corpus["snapshot_id"], "synthetic", query, vector) == []
