"""Stage 6 metric integrity, cold/warm controls and blinded paired packets; no provider calls."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from research.retrieval.stage6.evaluation import (
    analyze_result, grouped_summaries, paired_cluster_intervals, quantile, summarize, validate_config, validate_labels,
)
from research.retrieval.stage6 import paired_outputs
from scripts.retrieval import run_member2_stage6 as runner


@pytest.fixture
def config():
    return json.loads(runner.CONFIG.read_text(encoding="utf-8"))


def query(qid="Q1", candidates=None):
    return {"query_id": qid, "concept_id": "A01", "purpose": "hint", "query": "synthetic " + qid,
            "eligible_candidate_ids": ["a", "b"] if candidates is None else candidates, "expected_route": "retrieve"}


def result(ids=None, method="metadata", count=2):
    ids = ["a", "b"] if ids is None else ids
    return SimpleNamespace(chunks=[SimpleNamespace(content_id=cid) for cid in ids], method=method,
        fallback_reason=None if ids else "no_eligible_content", eligible_count=count, elapsed_ms=1,
        request_id=uuid4(), retrieval_id=uuid4())


def analyzed(q=None, res=None, labels=None, repeat=0):
    return analyze_result(q or query(), res or result(), wall_ms=10, embedding_calls=0,
        phase="query_cache_cold_model_warm" if not repeat else "query_cache_warm", repeat=repeat,
        dataset="synthetic", labels=labels)


def test_source_cohorts_pin_thirteen_concepts_and_keep_unjudged_quality_unavailable(config):
    manifest, corpus, cohorts = runner.load_inputs(config)
    assert manifest["concept_count"] == 13 and len(corpus["documents"]) == 91
    assert len(cohorts[0]["queries"]) == 104 and len(cohorts[1]["queries"]) == 156
    assert cohorts[0]["labels"] is not None and cohorts[1]["labels"] is None
    assert all(set(q["eligible_candidate_ids"]).issubset({d["content_id"] for d in corpus["documents"]})
               for cohort in cohorts for q in cohort["queries"])


@pytest.mark.parametrize("field,value", [("formal_test", True), ("warm_repeats", True), ("warm_repeats", 6),
    ("cutoffs", [5]), ("methods", ["hybrid"]), ("relevance_threshold", 1), ("bootstrap_cluster", "query_id")])
def test_protocol_rejects_uncontrolled_comparisons(config, field, value):
    config[field] = value
    with pytest.raises(ValueError):
        validate_config(config)


def test_unjudged_labels_are_never_converted_to_zero():
    queries = [query()]
    qrels = [{"query_id": "Q1", "content_id": cid, "relevance": None} for cid in ("a", "b")]
    validate_labels(queries, qrels, unjudged=True)
    with pytest.raises(ValueError, match="Unknown labels"):
        validate_labels(queries, qrels, unjudged=False)
    summary = summarize([analyzed()])
    assert summary["cutoffs"] is None and summary["unjudged_queries"] == 1


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "foreign", "boolean"))
def test_relevance_coverage_is_exhaustive_and_version_scope_cannot_be_bypassed(mutation):
    rows = [{"query_id": "Q1", "content_id": cid, "relevance": 2} for cid in ("a", "b")]
    if mutation == "missing": rows.pop()
    elif mutation == "duplicate": rows.append(deepcopy(rows[0]))
    elif mutation == "foreign": rows[0]["content_id"] = "forbidden"
    else: rows[0]["relevance"] = True
    with pytest.raises(ValueError):
        validate_labels([query()], rows, unjudged=False)


def test_no_positive_empty_query_has_na_metrics_and_separate_fallback_count():
    q = query(candidates=[])
    q["expected_route"] = "empty"
    row = analyzed(q, result([], count=0), {})
    summary = summarize([row])
    assert summary["cutoffs"]["5"]["recall"] == {"mean": None, "defined_queries": 0, "undefined_queries": 1}
    assert summary["empty_controls"] == {"unique_queries": 1, "requests": 1, "returned_empty": 1}


def test_cache_repeats_are_latency_samples_not_independent_quality_labels():
    rows = [analyzed(labels={"a": 2, "b": 1}, repeat=repeat) for repeat in (1, 2)]
    summary = summarize(rows)
    assert summary["executed_requests"] == 2 and summary["unique_queries"] == 1
    assert summary["quality_labelled_queries"] == 1 and summary["wall_ms"]["samples"] == 2
    assert summary["cutoffs"]["1"]["ndcg"]["defined_queries"] == 1


def test_partial_only_metrics_and_percentiles_preserve_definitions():
    summary = summarize([analyzed(labels={"a": 1, "b": 0})])
    assert summary["cutoffs"]["1"]["ndcg"]["mean"] == 1
    assert summary["cutoffs"]["1"]["recall"]["mean"] is None
    assert quantile([0, 10], .95) == 9.5 and quantile([], .95) is None


@pytest.mark.parametrize("mutation", ("forbidden", "incomplete", "error_fallback", "duplicate"))
def test_runtime_failures_are_not_successful_empty_fallbacks(mutation):
    res = result()
    if mutation == "forbidden": res.chunks[0].content_id = "private"
    elif mutation == "incomplete": res.chunks.pop()
    elif mutation == "duplicate": res.chunks[1].content_id = res.chunks[0].content_id
    else: res.fallback_reason = "retrieval_unavailable"
    with pytest.raises(ValueError):
        analyzed(res=res)


def test_cluster_intervals_resample_concepts_and_are_reproducible():
    rows = []
    for cid in ("A01", "A04"):
        for index in range(3):
            q = query(cid + str(index))
            q["concept_id"] = cid
            for method, ids in (("metadata", ["b", "a"]), ("semantic", ["a", "b"])):
                rows.append(analyzed(q, result(ids, method), {"a": 2, "b": 0}))
    first = paired_cluster_intervals(rows, 100, 123)
    assert first == paired_cluster_intervals(rows, 100, 123)
    assert first["ndcg@1"]["concept_clusters"] == 2
    assert first["ndcg@1"]["defined_queries"] == 6
    assert first["ndcg@1"]["semantic_minus_metadata"] == 1
    assert first["ndcg@1"]["ci95"] == [1, 1]


def test_runner_applies_the_same_candidates_and_avoids_warm_query_embedding(monkeypatch, config):
    class Embedder:
        calls = 0

        @lru_cache(maxsize=128)
        def _cached_query(self, text):
            self.calls += 1
            return (1, 0)

        def embed_query(self, text):
            return self._cached_query(text)

    class Retriever:
        def __init__(self, embedder): self.embedder = embedder

        def retrieve(self, request):
            q, method = request
            if method == "semantic" and q["eligible_candidate_ids"]:
                self.embedder.embed_query(q["query"])
            return result(q["eligible_candidate_ids"], method, len(q["eligible_candidate_ids"]))

    monkeypatch.setattr(runner, "KBRetriever", Retriever)
    monkeypatch.setattr(runner, "make_request", lambda projection, q, method: (q, method))
    cohorts = [{"name": "synthetic", "queries": [query()], "labels": {"Q1": {"a": 2, "b": 1}}}]
    embedder = Embedder()
    rows, cache = runner.run_retrieval(cohorts, None, embedder, config, lambda value: None)
    assert len(rows) == 6 and embedder.calls == 1
    assert sum(row["embedding_texts_computed"] for row in rows) == 1
    assert len(cache) == 3 and len(grouped_summaries(rows)) == 4


def test_paired_scenarios_cover_the_exact_thirteen_concepts_and_all_error_fixtures():
    _, bank, _ = runner.load_source("member2-v2")
    scenarios = paired_outputs.scenarios(bank, "synthetic-snapshot")
    assert len(scenarios) == 104
    assert sum(s["scenario_class"] == "wrong_submission" for s in scenarios) == 39
    assert {s["concept_id"] for s in scenarios} == {p.concept_id for p in bank.packs}
    assert all(not s["common_state"]["llm_allowed"] for s in scenarios)
    assert len({s["common_state_sha256"] for s in scenarios}) == 104


def test_pairing_calls_the_same_graph_and_preserves_the_common_state(monkeypatch):
    _, bank, _ = runner.load_source("member2-v2")
    chosen = paired_outputs.scenarios(bank, "synthetic-snapshot")[:1]
    before = deepcopy(chosen)

    class Graph:
        def invoke(self, state):
            full = state["teaching"]["mode"] == "full"
            return {"eligibility_preview": {"eligible": False, "reason": "not_target_evidence"},
                "validation": {"assessment": {"assessment_id": str(uuid4()), "assessment_status": "unverified"}},
                "policy": {"action": "hint"},
                "teaching_context": ["synthetic"] if full else [],
                "response": {"response_source": "reviewed_kb" if full else "reviewed_hint", "message": "Same hint",
                             "content_refs": ["synthetic"] if full else []}}

    monkeypatch.setattr(paired_outputs, "scenarios", lambda *args: chosen)
    monkeypatch.setattr(paired_outputs, "build_graph", lambda: Graph())
    pairs = paired_outputs.run_pairs(bank, "synthetic-snapshot")
    assert chosen == before and pairs[0]["same_message"]
    packet, key, template = paired_outputs.blind_packet(pairs, 123)
    serialized = json.dumps(packet)
    assert "full" not in serialized and "no_rag" not in serialized and "reviewed_kb" not in serialized
    assert set(key[0]["configuration_by_label"].values()) == {"full", "no_rag"}
    assert template["reviewer"] is None
    assert all(score is None for row in template["pairs"] for response in row["responses"].values()
               for score in response["scores"].values())
    summary = paired_outputs.summarize_pairs(pairs)
    assert summary["quality_ratings"] is None and summary["session_writes"] == 0


def test_assessment_comparison_ignores_only_the_invocation_id():
    a = {"assessment_id": "one", "assessment_status": "verified_incorrect", "first_error_step": 1,
         "validator_version": "synthetic-1"}
    b = {**a, "assessment_id": "two"}
    assert paired_outputs.assessment_signature(a) == paired_outputs.assessment_signature(b)
    for field, value in (("assessment_status", "verified_correct"), ("first_error_step", 2),
                         ("validator_version", "synthetic-2")):
        assert paired_outputs.assessment_signature(a) != paired_outputs.assessment_signature({**b, field: value})
