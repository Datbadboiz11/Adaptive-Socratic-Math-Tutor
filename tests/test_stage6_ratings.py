"""Synthetic reviewers only: integrity, rubric direction, N/A and disagreement handling."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from research.retrieval.dataset import json_bytes, sha256, write_new_bundle
from research.retrieval.stage6.paired_outputs import blind_packet
from research.retrieval.stage6.ratings import compare_reviews, load_run, validate_review


@pytest.fixture
def ratings():
    pairs = [{"scenario_id": "SYNTHETIC-" + str(i), "concept_id": ("A01", "A04")[i // 2],
              "common_state_sha256": "0" * 64, "prompt": "Synthetic task", "steps": ["wrong"] if i % 2 == 0 else [],
              "action": "submit" if i % 2 == 0 else "request_hint", "prior_hint_level": 0,
              "scenario_class": "wrong_submission" if i % 2 == 0 else "support_request",
              "variants": {mode: {"response": {"message": "Synthetic teaching text"}}
                           for mode in ("full", "no_rag")}} for i in range(4)]
    packet, key, template = blind_packet(pairs, 123)
    mapping = {row["pair_id"]: row for row in key}
    applicable = {row["pair_id"]: row["error_alignment_applicable"] for row in packet["pairs"]}
    reviews = []
    for slot in ("A", "B"):
        review = deepcopy(template)
        review.update(reviewer="SYNTHETIC reviewer " + slot,
                      reviewed_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
        for pair in review["pairs"]:
            for label, response in pair["responses"].items():
                full = mapping[pair["pair_id"]]["configuration_by_label"][label] == "full"
                for criterion in response["scores"]:
                    response["scores"][criterion] = (0 if full else 1) if criterion == "answer_disclosure" else (2 if full else 1)
                if not applicable[pair["pair_id"]]:
                    response["scores"]["error_alignment"] = None
        reviews.append(review)
    return packet, key, reviews


def test_consensus_keeps_disclosure_direction_and_na_correct(ratings):
    packet, key, (first, second) = ratings
    result = compare_reviews(first, second, packet, key, samples=100)
    assert result["status"] == "agreed" and not result["formal_test_ready"]
    assert result["agreement"]["mathematics"]["rated_responses"] == 8
    assert result["agreement"]["error_alignment"]["rated_responses"] == 4
    for criterion, summary in result["quality_summary"].items():
        assert summary["improvement_for_full"] == 1
        assert summary["ci95"] == [1, 1] and summary["concept_clusters"] == 2
    assert result["quality_summary"]["answer_disclosure"]["mean_by_configuration"] == {"full": 0, "no_rag": 1}
    assert "lower_disclosure" in result["quality_summary"]["answer_disclosure"]["direction"]


def test_disagreement_is_preserved_without_averaging(ratings):
    packet, key, (first, second) = ratings
    value = second["pairs"][0]["responses"]["A"]["scores"]["mathematics"]
    second["pairs"][0]["responses"]["A"]["scores"]["mathematics"] = 0 if value else 1
    result = compare_reviews(first, second, packet, key)
    assert result["status"] == "needs_adjudication" and result["quality_summary"] is None
    assert len(result["conflicts"]) == 1
    assert result["agreement"]["mathematics"]["exact_agreement"] == .875


@pytest.mark.parametrize("mutation", ["same_person", "stale_packet", "missing_pair", "duplicate_pair", "boolean",
    "unjudged", "na_as_zero", "missing_criterion", "missing_arm", "future", "naive_time", "ai_method", "rubric"])
def test_partial_or_invalid_ratings_never_become_a_quality_claim(ratings, mutation):
    packet, key, (first, second) = ratings
    scores = second["pairs"][0]["responses"]["A"]["scores"]
    if mutation == "same_person": second["reviewer"] = "  " + first["reviewer"].upper()
    elif mutation == "stale_packet": second["packet_sha256"] = "0" * 64
    elif mutation == "missing_pair": second["pairs"].pop()
    elif mutation == "duplicate_pair": second["pairs"].append(deepcopy(second["pairs"][0]))
    elif mutation == "boolean": scores["mathematics"] = True
    elif mutation == "unjudged": scores["mathematics"] = None
    elif mutation == "na_as_zero":
        not_applicable = next(row["pair_id"] for row in packet["pairs"] if not row["error_alignment_applicable"])
        next(row for row in second["pairs"] if row["pair_id"] == not_applicable)["responses"]["A"]["scores"]["error_alignment"] = 0
    elif mutation == "missing_criterion": scores.pop("mathematics")
    elif mutation == "missing_arm": second["pairs"][0]["responses"].pop("B")
    elif mutation == "future": second["reviewed_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif mutation == "naive_time": second["reviewed_at"] = "2026-01-01T00:00:00"
    elif mutation == "ai_method": second["method"] = "ai_assisted"
    else: second["criteria"] = {**second["criteria"], "mathematics": "Changed rubric"}
    with pytest.raises(ValueError):
        compare_reviews(first, second, packet, key)


def test_signed_review_cannot_refer_to_an_incomplete_or_wrong_key(ratings):
    packet, key, reviews = ratings
    with pytest.raises(ValueError, match="key coverage"):
        compare_reviews(*reviews, packet, key[:-1])
    key[0]["configuration_by_label"] = {"A": "full", "B": "full"}
    with pytest.raises(ValueError, match="mapping"):
        compare_reviews(*reviews, packet, key)


def test_run_loader_requires_immutable_packet_and_key(tmp_path, ratings):
    packet, key, _ = ratings
    files = {"paired-blind.json": json_bytes(packet), "paired-key.json": json_bytes(key),
             "report.json": json_bytes({"owner": "Member 2", "concept_ids": list(range(13))})}
    files["manifest.json"] = json_bytes({"status": "dev_evaluation_completed", "formal_test_ready": False,
                                         "files_sha256": {name: sha256(content) for name, content in files.items()}})
    write_new_bundle(tmp_path, files)
    assert load_run(tmp_path)[0] == packet
    target = tmp_path / "paired-blind.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_run(tmp_path)
