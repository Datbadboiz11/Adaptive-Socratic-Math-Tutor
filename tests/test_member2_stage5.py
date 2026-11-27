"""Member 2's Stage 5 scope is independent of other owners; review identities here are synthetic."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from app.kb_projection import load_source
from app.member2_foundation import load_workboard
from research.retrieval.dataset import (
    audit_splits, blocking_reasons, compare_reviews, json_bytes, make_workset,
    sha256, validate_bundle, write_new_bundle,
)
from scripts.retrieval import curate_stage5, prepare_member2_stage5 as prepare


@pytest.fixture(scope="module")
def assets():
    return prepare.build_assets()


@pytest.fixture
def data(assets):
    return tuple(json.loads(assets[prepare.DATASET + "/" + name])
                 for name in ("manifest.json", "corpus.json", "queries.json", "qrels.unjudged.json"))


def test_default_workset_contains_exactly_the_assigned_thirteen_concepts(assets, data):
    manifest, corpus, queries, qrels = data
    assignment = next(row for row in load_workboard().assignments if row.owner == "Member 2")
    assigned = set(assignment.concept_ids)
    assert set(manifest["concept_ids"]) == {q["concept_id"] for q in queries} == assigned
    assert {doc["concept_id"] for doc in corpus["documents"]} == assigned
    assert len(queries) == 156 and len(corpus["documents"]) == 91 and len(qrels) == 195
    assert manifest["missing_content_queries"] == 0 and manifest["split_counts"] == {"dev": 156}
    assert all(q["content_status"] == "ready" for q in queries)
    assert all(name.startswith(prepare.DATASET + "/") for name in assets)
    assert not any("stage5-expansion" in name or "coverage40" in name for name in manifest["source_sha256"])
    assert all(row["relevance"] is None for row in qrels)
    assert curate_stage5.DEFAULT == ROOT / prepare.DATASET


def test_thirteen_concept_content_and_taxonomy_coverage_are_separate_from_review(assets):
    coverage = json.loads(assets[prepare.DATASET + "/coverage.json"])
    taxonomy = json.loads(assets[prepare.DATASET + "/misconception-taxonomy.json"])
    _, bank, _ = load_source("member2-v2")
    assert coverage["summary"] == {
        "owned_concepts": 13, "approved_packs": 13, "approved_problems": 78, "approved_examples": 39,
        "error_fixtures": 39, "proposed_error_categories": 32, "query_count": 156,
        "concepts_awaiting_reviewed_content": 0}
    expected = {error.error_id: error for pack in bank.packs for error in pack.errors}
    assert len(taxonomy["mappings"]) == len(expected) == 39
    assert {row["error_id"] for row in taxonomy["mappings"]} == set(expected)
    categories = {row["category_id"] for row in taxonomy["categories"]}
    assert len(categories) == 32 and not taxonomy["runtime_publication"]
    for row in taxonomy["mappings"]:
        assert row["category_id"] in categories
        assert row["mapping_review_status"] == "proposed_pending_independent_review"
        assert expected[row["error_id"]].problem_id == row["problem_id"]
        assert expected[row["error_id"]].first_error_step == row["first_error_step"]
    # Multiple fixtures share a category instead of inflating the taxonomy count.
    signed = [row for row in taxonomy["mappings"] if row["concept_id"] == "N02"]
    assert len({row["category_id"] for row in signed}) == 1


@pytest.mark.parametrize("cid", sorted(prepare.INTENTS))
def test_each_concept_has_hint_levels_examples_and_control_routes(data, cid):
    _, corpus, queries, qrels = data
    selected = [q for q in queries if q["concept_id"] == cid]
    assert len(selected) == 12
    assert {q["allowed_hint_level"] for q in selected if q["purpose"] == "hint"} == {1, 2, 3}
    assert {q["expected_route"] for q in selected} == {"retrieve", "empty", "clarify", "out_of_scope"}
    for q in selected:
        if q["expected_route"] in ("empty", "clarify", "out_of_scope"):
            assert not q["eligible_candidate_ids"]
        elif q["purpose"] == "example":
            assert len(q["eligible_candidate_ids"]) == 2
        for doc in corpus["documents"]:
            if doc["content_id"] in q["eligible_candidate_ids"]:
                assert not blocking_reasons(doc, q)
                if doc["kind"] == "example":
                    assert doc["family_id"] not in q["excluded_family_ids"]
    assert len([row for row in qrels if any(row["query_id"] == q["query_id"] for q in selected)]) == 15


def test_every_document_version_is_pinned_and_unknown_labels_stay_null(data):
    _, corpus, queries, qrels = data
    docs = {doc["content_id"]: doc for doc in corpus["documents"]}
    assert qrels == make_workset(corpus, deepcopy(queries))
    for row in qrels:
        assert row["content_sha256"] == sha256(json_bytes(docs[row["content_id"]]))
        assert row["content_version"] == docs[row["content_id"]]["content_version"]
        assert row["relevance"] is None and row["label_status"] == "unjudged"


def test_other_members_are_waiting_and_do_not_block_current_scope(assets, data):
    manifest, _, queries, _ = data
    integration = json.loads(assets[prepare.DATASET + "/integration-status.json"])
    assert not integration["blocks_current_scope"]
    assert {row["owner"] for row in integration["waiting_for"]} == {"Member 1", "Member 3"}
    assert sum(len(row["concept_ids"]) for row in integration["waiting_for"]) == 27
    assert all(row["status"] == "awaiting_owner_delivery" and row["source_manifest"] is None
               for row in integration["waiting_for"])
    status = curate_stage5.readiness(manifest, queries)
    assert status["concepts_awaiting_reviewed_content"] == []
    assert not status["other_members_block_current_scope"]
    assert "content_and_scope_review" not in status["freeze_blockers"]
    assert "independent_query_and_label_reviews" in status["freeze_blockers"]
    assert not status["formal_test_ready"]


def test_foreign_or_missing_pack_is_refused_before_projection(monkeypatch):
    original = prepare.load_source
    registry, bank, origin = original("member2-v2")
    bank.packs.pop()
    monkeypatch.setattr(prepare, "load_source", lambda source: (registry, bank, origin))
    with pytest.raises(ValueError, match="exactly the Member 2"):
        prepare.approved_inputs()


def test_existing_intents_cannot_be_relabelled_as_test(data):
    manifest, _, queries, _ = data
    queries[0]["split"] = "test_candidate"
    with pytest.raises(ValueError, match="Historical dev"):
        audit_splits(queries, manifest["reserved_dev_concepts"])


def completed_template(assets, slot, selection="pilot"):
    review = json.loads(assets[f"{prepare.DATASET}/{selection}-review-{slot}.template.json"])
    review.update(reviewer="SYNTHETIC reviewer " + slot,
                  reviewed_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    for query in review["queries"]:
        query.update(checked=True, query_accepted=True)
    for row in review["judgments"]:
        row["relevance"] = 2
    return review


def test_pilot_and_full_review_templates_have_complete_candidate_coverage(assets, data):
    manifest, _, queries, qrels = data
    for selection, count, judgments in (("pilot", 26, 39), ("full", 156, 195)):
        a, b = (completed_template(assets, slot, selection) for slot in ("A", "B"))
        assert len(a["queries"]) == count and len(a["judgments"]) == judgments
        result = compare_reviews(a, b, manifest, queries, qrels)
        assert result["status"] == "agreed" and len(result["qrels"]) == judgments
        assert not result["formal_test_ready"]
    assert "Relevance (0/1/2): ___" in assets[prepare.DATASET + "/pilot-review.md"].decode("utf-8")


@pytest.mark.parametrize("mutation", ("same_person", "missing_label", "stale_hash", "forbidden_doc", "bool_label", "disagree"))
def test_review_integrity_is_preserved_in_scoped_workset(assets, data, mutation):
    manifest, _, queries, qrels = data
    a, b = (completed_template(assets, slot) for slot in ("A", "B"))
    if mutation == "same_person":
        b["reviewer"] = "  " + a["reviewer"].upper()
    elif mutation == "missing_label":
        b["judgments"].pop()
    elif mutation == "stale_hash":
        b["judgments"][0]["content_sha256"] = "0" * 64
    elif mutation == "forbidden_doc":
        b["judgments"][0]["content_id"] = "N03-explanation"
    elif mutation == "bool_label":
        b["judgments"][0]["relevance"] = True
    else:
        b["judgments"][0]["relevance"] = 1
        result = compare_reviews(a, b, manifest, queries, qrels)
        assert len(result["conflicts"]) == 1 and not result["qrels"]
        return
    with pytest.raises(ValueError):
        compare_reviews(a, b, manifest, queries, qrels)


def test_generated_bundle_validates_and_existing_work_is_never_replaced(assets, tmp_path):
    write_new_bundle(tmp_path, assets)
    validate_bundle(tmp_path / prepare.DATASET)
    with pytest.raises(ValueError, match="exists"):
        write_new_bundle(tmp_path, assets)
    target = tmp_path / prepare.DATASET / "queries.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_bundle(tmp_path / prepare.DATASET)


def test_full_template_cli_reads_current_scoped_dataset(assets, data, tmp_path, monkeypatch, capsys):
    output = tmp_path / "full-A.json"
    monkeypatch.setattr(curate_stage5, "validate_bundle", lambda *args: data)
    monkeypatch.setattr(sys, "argv", ["curate", "template", "--selection", "full", "--slot", "A", "--output", str(output)])
    assert curate_stage5.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert len(result["queries"]) == 156 and len(result["judgments"]) == 195
    assert json.loads(capsys.readouterr().out)["status"] == "pending_review"
