"""Stage 5 arithmetic, split isolation and review integrity; review identities are synthetic."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from app.authoring_math import audit_case, first_error
from app.content_authoring import DraftRequest, check_draft
from app.curriculum import CurriculumRegistry, PilotBank, load_curriculum
from app.kb_projection import load_profile, project
from research.retrieval.dataset import (
    audit_splits, blocking_reasons, compare_reviews, json_bytes, make_workset,
    review_template, sha256, validate_bundle, validate_review, write_new_bundle,
)
from scripts.retrieval.prepare_stage5 import DATASET, DRAFTS, build_assets


@pytest.fixture(scope="module")
def assets():
    return build_assets()


@pytest.fixture
def data(assets):
    return tuple(json.loads(assets[DATASET + "/" + name])
                 for name in ("manifest.json", "corpus.json", "queries.json", "qrels.unjudged.json"))


@pytest.fixture
def reviews(assets):
    result = []
    for slot in ("A", "B"):
        review = json.loads(assets[DATASET + f"/pilot-review-{slot}.template.json"])
        review.update(reviewer="SYNTHETIC reviewer " + slot,
                      reviewed_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
        for query in review["queries"]:
            query.update(checked=True, query_accepted=True)
        for judgment in review["judgments"]:
            judgment["relevance"] = 2
        result.append(review)
    return result


def test_inventory_and_candidate_splits_are_honest(assets, data):
    manifest, corpus, queries, qrels = data
    coverage = json.loads(assets[DATASET + "/coverage.json"])
    assert coverage["summary"] == {
        "registry_concepts": 40, "concepts_with_pack": 22, "approved_serving_concepts": 13,
        "new_draft_concepts": 2, "problems_in_distinct_concept_packs": 132,
        "examples_in_distinct_concept_packs": 66, "missing_approved_problems": 162,
        "missing_approved_examples": 81}
    assert len(queries) == 160 and len(corpus["documents"]) == 91 and len(qrels) == 64
    assert manifest["split_counts"] == {"dev": 88, "test_candidate": 72}
    assert len(manifest["pilot_query_ids"]) == 26
    assert len({q["concept_id"] for q in queries}) == 40
    assert all(sum(q["concept_id"] == cid for q in queries) == 4 for cid in {q["concept_id"] for q in queries})
    assert all(row["relevance"] is None and row["label_status"] == "unjudged" for row in qrels)
    assert all(q["content_status"] == "awaiting_reviewed_content" for q in queries if q["split"] == "test_candidate")
    assert manifest["missing_content_queries"] == 108
    assert {q["allowed_hint_level"] for q in queries if q["content_status"] == "ready" and q["purpose"] == "hint"} == {1, 2, 3}
    assert {q["query_class"] for q in queries if q["content_status"] == "ready" and q["query_id"].endswith("CONTROL")} == {
        "ambiguous", "out_of_scope", "no_eligible_content"}
    n04 = next(row for row in coverage["concepts"] if row["concept_id"] == "N04")
    assert "reduced_fraction_form_not_measured_by_numeric_equivalence" in n04["blockers"]


def test_new_drafts_pass_exact_checks_and_remain_unpublished(assets):
    from sympy import simplify, sympify

    registry = CurriculumRegistry.model_validate_json(assets[DRAFTS + "/registry-snapshot.json"])
    bank = PilotBank.model_validate_json(assets[DRAFTS + "/draft-bank.json"])
    _, existing = load_curriculum(revision="v2")
    assert {pack.concept_id for pack in bank.packs} == {"N03", "N06"}
    for pack in bank.packs:
        request = DraftRequest.model_validate_json(assets[f"{DRAFTS}/{pack.concept_id}/request.json"])
        assert check_draft(pack, request, registry, existing).passed
        assert pack.review.status == "draft" and pack.review.human_reviewer is None
        for case in [*pack.problems, *pack.examples]:
            audit_case(case)
            # Independent symbolic engine, using only the bounded original
            # numeric drafts above; this does not reuse authoring_math.scalar.
            target = sympify(case.task.expression, rational=True)
            assert simplify(target - sympify(case.reference_answer, rational=True)) == 0
            assert all(simplify(target - sympify(step, rational=True)) == 0 for step in case.reference_steps)
        for error in pack.errors:
            problem = next(p for p in pack.problems if p.case_id == error.problem_id)
            assert first_error(problem, error.response_steps) == error.first_error_step
            assert simplify(sympify(problem.task.expression, rational=True)
                            - sympify(error.response_steps[0], rational=True)) != 0
    projection = project(registry, bank, load_profile(), origin="stage5-unpublished-test")
    assert not projection.chunks
    assert {row["concept_id"] for row in projection.blocked} == {"N03", "N06"}


@pytest.mark.parametrize("mutation", ["concept", "intent", "source", "family", "lineage", "cross_field", "duplicate", "historical"])
def test_split_audit_rejects_leakage(data, mutation):
    manifest, _, queries, _ = data
    dev = next(q for q in queries if q["split"] == "dev")
    test = next(q for q in queries if q["split"] == "test_candidate")
    if mutation == "concept":
        test["concept_id"] = dev["concept_id"]
    elif mutation == "intent":
        test["intent_group"] = dev["intent_group"]
    elif mutation == "duplicate":
        test["query"] = "  " + dev["query"].upper() + "  "
    elif mutation == "historical":
        dev["split"] = "test_candidate"
    elif mutation == "cross_field":
        dev["excluded_family_ids"] = test["excluded_lineage_ids"] = ["SYNTHETIC-SHARED-GROUP"]
    else:
        field = {"source": "excluded_source_groups", "family": "excluded_family_ids", "lineage": "excluded_lineage_ids"}[mutation]
        dev[field] = test[field] = ["SYNTHETIC-SHARED-GROUP"]
    with pytest.raises(ValueError):
        audit_splits(queries, manifest["reserved_dev_concepts"])


@pytest.mark.parametrize("field,value,reason", [
    ("hint_level", 3, "hint_level"), ("review", {"status": "draft"}, "review"),
    ("grade_levels", [12], "grade"), ("difficulty", "standard", "difficulty"),
    ("problem_id", "SYNTHETIC-ACTIVE", "active_problem"), ("source_group", "SYNTHETIC-SOURCE", "source_group"),
    ("family_id", "SYNTHETIC-FAMILY", "family"), ("lineage_ids", ["SYNTHETIC-LINEAGE"], "lineage"),
])
def test_scope_blocking_reasons(data, field, value, reason):
    _, corpus, queries, _ = data
    document = next(doc for doc in corpus["documents"] if doc["kind"] == "example")
    query = next(q for q in queries if q["concept_id"] == document["concept_id"] and q["purpose"] == "example")
    query.update(active_problem_id="SYNTHETIC-ACTIVE", excluded_source_groups=["SYNTHETIC-SOURCE"],
                 excluded_family_ids=["SYNTHETIC-FAMILY"], excluded_lineage_ids=["SYNTHETIC-LINEAGE"],
                 difficulty="introductory", allowed_hint_level=2 if field == "hint_level" else 3)
    document[field] = value
    assert reason in blocking_reasons(document, query)


def test_unknown_content_is_not_a_successful_empty_fallback(data):
    _, corpus, queries, _ = data
    waiting = next(q for q in queries if q["content_status"] != "ready")
    assert not waiting["eligible_candidate_ids"]
    waiting["content_status"] = "ready"
    with pytest.raises(ValueError, match="readiness"):
        make_workset(corpus, queries)


def test_review_agreement_and_disagreement_preserve_independent_labels(data, reviews):
    manifest, _, queries, qrels = data
    first, second = reviews
    agreed = compare_reviews(first, second, manifest, queries, qrels)
    assert agreed["exact_agreement"] == 1 and agreed["cohen_kappa"] is None
    assert agreed["status"] == "agreed" and not agreed["formal_test_ready"]
    assert len(agreed["qrels"]) == len(first["judgments"])
    second["judgments"][0]["relevance"] = 1
    result = compare_reviews(first, second, manifest, queries, qrels)
    assert result["status"] == "needs_adjudication" and len(result["conflicts"]) == 1
    assert result["qrels"] == [] and first["judgments"][0]["relevance"] == 2


@pytest.mark.parametrize("mutation", ["same_person", "stale_corpus", "stale_query", "stale_document", "missing",
                                     "unknown", "duplicate", "bool", "null", "future", "naive", "unchecked", "selection"])
def test_reviews_reject_incomplete_or_inconsistent_input(data, reviews, mutation):
    manifest, _, queries, qrels = data
    first, second = reviews
    row = second["judgments"][0]
    if mutation == "same_person":
        second["reviewer"] = "  " + first["reviewer"].upper()
    elif mutation == "stale_corpus":
        second["corpus_sha256"] = "0" * 64
    elif mutation == "stale_query":
        second["queries_sha256"] = "0" * 64
    elif mutation == "stale_document":
        row["content_sha256"] = "0" * 64
    elif mutation == "missing":
        second["judgments"].pop()
    elif mutation == "unknown":
        row["content_id"] = "SYNTHETIC-FORBIDDEN"
    elif mutation == "duplicate":
        second["judgments"].append(deepcopy(row))
    elif mutation == "bool":
        row["relevance"] = True
    elif mutation == "null":
        row["relevance"] = None
    elif mutation == "future":
        second["reviewed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif mutation == "naive":
        second["reviewed_at"] = "2026-01-01T00:00:00"
    elif mutation == "unchecked":
        second["queries"][0]["checked"] = False
    else:
        second["queries"].pop()
    with pytest.raises(ValueError):
        compare_reviews(first, second, manifest, queries, qrels)


def test_missing_content_cannot_be_reviewed_as_final_test(data):
    manifest, _, queries, qrels = data
    selected = [q["query_id"] for q in queries if q["split"] == "test_candidate"]
    review = review_template(manifest["dataset_id"], manifest["files_sha256"]["corpus.json"],
                             manifest["files_sha256"]["queries.json"], queries, qrels, selected, "A")
    review.update(reviewer="SYNTHETIC reviewer", reviewed_at="2026-01-01T00:00:00+00:00")
    for query in review["queries"]:
        query.update(checked=True, query_accepted=True)
    with pytest.raises(ValueError, match="Content not ready"):
        validate_review(review, manifest, queries, qrels)


def test_bundle_detects_tampering_and_forbidden_content(assets, data, tmp_path):
    write_new_bundle(tmp_path, assets)
    validate_bundle(tmp_path / DATASET)
    target = tmp_path / DATASET / "queries.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_bundle(tmp_path / DATASET)
    _, corpus, queries, _ = data
    corpus["documents"][0]["review"] = {"status": "draft", "author": "SYNTHETIC", "source": "SYNTHETIC"}
    with pytest.raises(ValueError, match="unpublished"):
        make_workset(corpus, queries)


def test_bundle_preflight_never_overwrites_existing_work_or_escapes(tmp_path):
    (tmp_path / "existing.json").write_text("user review", encoding="utf-8")
    with pytest.raises(ValueError):
        write_new_bundle(tmp_path, {"new.json": b"new", "existing.json": b"changed"})
    assert not (tmp_path / "new.json").exists()
    assert (tmp_path / "existing.json").read_text(encoding="utf-8") == "user review"
    with pytest.raises(ValueError):
        write_new_bundle(tmp_path, {"../escape.json": b"invalid"})
