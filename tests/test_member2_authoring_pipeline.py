"""Current authoring entry points use 13 configs and immutable source snapshots."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts/checks"), str(ROOT / "scripts/authoring")]

from app.authoring_runs import (
    RunStore, authoring_prompt, check_run, create_run, load_authoring_source, load_json, review_run,
)
from app.content_authoring import ContentReview, DraftRequest, MEMBER2_PROMPT_VERSION, review_template
from app.curriculum import ConceptPack
from check_authoring import audit
from prepare_member2_pilot import rendered_pilot

CONFIGS = sorted((ROOT / "content/authoring/configs/member2-v2").glob("*.json"))


@pytest.mark.parametrize("config", CONFIGS, ids=lambda path: path.stem)
def test_current_concept_draft_and_check_entry_points(config):
    request = DraftRequest.model_validate(load_json(config))
    registry, _ = load_authoring_source("member2-v2")
    prompt = authoring_prompt(request, registry, "member2-v2")
    context = json.loads(prompt[1]["content"])
    assert context["prompt_version"] == MEMBER2_PROMPT_VERSION
    assert context["concept"]["concept_id"] == config.stem
    assert context["concept"]["authoring_task_kinds"]
    slots = context["required_problem_slots"]
    assert [slot["case_id"] for slot in slots] == [request.id_prefix + f"P-{index:02}" for index in range(1, 7)]
    assert [slot["family_id"] for slot in slots] == [family.family_id for family in request.families for _ in range(2)]
    assert context["request"]["content_version"] == "0.4.0-member2-review"
    store = RunStore(ROOT / "artifacts/authoring-tests" / uuid4().hex)
    path, manifest = create_run(request, "replay", "pilot_replay", store=store, source="member2-v2")
    assert manifest["status"] == "draft_ready" and manifest["generation"]["model_calls"] == 0
    assert manifest["source"] == "member2-v2" and manifest["prompt_version"] == MEMBER2_PROMPT_VERSION
    assert {"registry-snapshot.json", "bank-snapshot.json"}.issubset(manifest["artifact_sha256"])
    assert check_run(path).passed


def test_current_review_uses_run_snapshot_and_keeps_approved_release_intact():
    config = ROOT / "content/authoring/configs/member2-v2/F05.json"
    request = DraftRequest.model_validate(load_json(config))
    source = ROOT / "content/authoring/batches/member2-original.v2/approved-bank.json"
    original = source.read_bytes()
    store = RunStore(ROOT / "artifacts/authoring-tests" / uuid4().hex)
    path, _ = create_run(request, "review", "pilot_replay", store=store, source="member2-v2")
    pack = ConceptPack.model_validate(load_json(path / "draft.json"))
    review = ContentReview.model_validate({**review_template(pack), "review_id": "SYNTHETIC-ONLY",
        "reviewer": "Synthetic independent reviewer", "reviewed_at": datetime.now(timezone.utc),
        "decision": "approved", "checklist": dict.fromkeys(review_template(pack)["checklist"], "pass"),
        "comments": "Synthetic lifecycle fixture only."})
    with patch("app.authoring_runs.load_curriculum", side_effect=AssertionError("Legacy registry must not be consulted")):
        assert check_run(path).passed
        destination, approved = review_run("review", review, store=store)
    assert approved and (destination / "approved-pack.json").is_file()
    assert load_json(path / "draft.json")["review"]["status"] == "draft"
    assert source.read_bytes() == original
    with (path / "bank-snapshot.json").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="artifact changed"):
        check_run(path)


def test_stage2_audit_is_scoped_to_13_and_never_reads_removed_pack_directories():
    def block_legacy_batch(path):
        if "a02-e02-" in str(path):
            raise AssertionError("Removed A02/E02 batch was accessed")
        return load_json(path)

    with patch("prepare_member2_pilot.load_json", side_effect=block_legacy_batch), \
            patch("app.authoring_runs.load_curriculum", side_effect=AssertionError("Legacy source accessed")):
        artifacts, summary = rendered_pilot("v2")
        results = audit()
    assert len(results) == 13 and {result["concept_id"] for result in results} == set(summary["member2_concepts"])
    assert not {"A02", "E02"}.intersection(result["concept_id"] for result in results)
    assert summary["original_replacements"] == [] and len(artifacts["draft-bank.json"]["packs"]) == 13


def test_member2_source_rejects_out_of_scope_or_wrong_version_before_any_model_call():
    request = DraftRequest.model_validate(load_json(CONFIGS[0]))
    store = RunStore(ROOT / "artifacts/authoring-tests" / uuid4().hex)
    for changes in ({"content_version": "0.1.0"}, {"concept_id": "A02"}):
        with pytest.raises(ValueError), patch("app.authoring_runs.generate_openai") as generate:
            create_run(request.model_copy(update=changes), "invalid", "openai", store=store, source="member2-v2")
        generate.assert_not_called()
    assert not store.root.exists()
