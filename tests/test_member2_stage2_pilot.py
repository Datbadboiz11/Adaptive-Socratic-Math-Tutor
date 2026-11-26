"""Regression coverage for the authoring pilot, source hold and Gemini boundary."""
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sys

import httpx
import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts/authoring")]

from app.authoring_math import expected, response_value
from app.authoring_extended_math import check_expanded_quadratic
from app.authoring_runs import RunStore, generate_gemini, load_json, pilot_replay
from app.content_authoring import ContentReview, DraftRequest, digest
from app.curriculum import AuthoringMathTask, ConceptPack, load_curriculum
from app.member2_contracts import project_problem
from app.member2_problem_contract import project_curriculum_problem
from prepare_member2_pilot import record_review, rendered_pilot


def test_original_pilot_covers_member2_and_separates_vertex_from_axis():
    artifacts, summary = rendered_pilot()
    assert len(summary["member2_concepts"]) == 13
    assert summary["original_replacements"] == ["A02", "E02"]
    assert sum(summary["packs"][cid]["problems"] for cid in summary["member2_concepts"]) == 78
    assert all(pack["review"] == "draft" for pack in summary["packs"].values())
    pack = ConceptPack.model_validate(artifacts["F05/draft.json"])
    axis = [problem for problem in pack.problems if problem.task.kind == "quadratic_axis"]
    assert len(axis) == 4
    with pytest.raises(ValueError, match="vertical"):
        response_value(axis[0].task, "y=3/2")
    with pytest.raises(ValidationError):
        project_problem(axis[0], pack.content_version)


def test_extended_math_rejects_equivalent_wrong_form_and_missing_domain():
    factor = AuthoringMathTask(kind="factored_polynomial", expression="18*x+30")
    for response in ("18*x+30", "3*(6*x+10)"):
        with pytest.raises(ValueError):
            response_value(factor, response)
    fraction = AuthoringMathTask(kind="rational_operation", expression="*; x-2|x+4; x+4|x-5")
    assert response_value(fraction, "x-2|x-5;{-4,5}") == expected(fraction)
    assert response_value(fraction, "x-2|x-5;{5}") != expected(fraction)


def test_review_edition_covers_all_assigned_concepts_and_keeps_drafts_private():
    artifacts, summary = rendered_pilot("v2")
    assert summary["reviewer"] == "Member 3"
    assert len(summary["member2_concepts"]) == 13
    assert set(summary["packs"]) == set(summary["member2_concepts"])
    assert summary["original_replacements"] == []
    assert summary["runtime_publication"] is False
    for concept_id in summary["member2_concepts"]:
        record = summary["packs"][concept_id]
        assert (record["problems"], record["examples"], record["error_fixtures"], record["hint_levels"]) == (6, 3, 3, 3)
        assert record["review"] == "draft"
        assert artifacts[f"{concept_id}/review.md"].count("**Ví dụ**") == 3
        assert artifacts[f"{concept_id}/review-template.json"]["reviewer"] is None

    pack = ConceptPack.model_validate(artifacts["E03/draft.json"])
    for problem in pack.problems:
        public = project_curriculum_problem(problem, pack.content_version)
        assert "=" not in public.task.expression
        assert problem.reference_answer not in public.model_dump_json()
        assert response_value(problem.task, problem.reference_answer.replace("positive_integer", "nguyên dương")) == expected(problem.task)

    rational = ConceptPack.model_validate(artifacts["A10/draft.json"])
    assert {problem.task.expression.split(';', 1)[0] for problem in rational.problems} == {"+", "-", "*", "/"}
    assert {problem.source_group for problem in rational.problems} == {
        problem["source_group"] for problem in rendered_pilot()[0]["A10/draft.json"]["problems"]
    }


def test_review_checkers_measure_form_domain_and_exact_irrational_roots():
    with pytest.raises(ValueError, match="Expand"):
        check_expanded_quadratic("4*x*(3*x-7)")
    with pytest.raises(ValueError, match="Collect"):
        check_expanded_quadratic("12*x*x-14*x-14*x")
    check_expanded_quadratic("12*x*x-28*x")

    roots = AuthoringMathTask(kind="quadratic_roots", expression="2*x*x+2*x-1")
    assert response_value(roots, "12;{(-2+sqrt(12))/4,(-2-sqrt(12))/4}") == expected(roots)
    assert response_value(roots, "12;{0.366,-1.366}") != expected(roots)
    with pytest.raises(ValueError):
        response_value(roots, "12;{sqrt(2)+sqrt(3)}")

    domain = AuthoringMathTask(kind="function_domain", expression="sqrt; 2*x+14")
    assert response_value(domain, "[−7, +∞)") == expected(domain)
    conversion = AuthoringMathTask(kind="number_conversion", expression="0.315 -> percent")
    assert response_value(conversion, "31,5%") == expected(conversion)

    powers = AuthoringMathTask(kind="exponent_numeric", expression="function;power;1/2;2;-2")
    assert response_value(powers, "(1/2)^-4=16;ℝ") == expected(powers)
    assert response_value(powers, "(1/2)^-4=16;R+") != expected(powers)
    invalid_base = AuthoringMathTask(kind="exponent_numeric", expression="base;1")
    assert response_value(invalid_base, "không phải hàm số mũ") == expected(invalid_base)


def test_review_edition_records_exact_review_material_and_rejects_edits(tmp_path):
    artifacts, summary = rendered_pilot("v2")
    (tmp_path / "A07").mkdir()
    names = ("registry-snapshot.json", "A07/request.json", "A07/draft.json")
    hashes = {name: RunStore.write(tmp_path / name, artifacts[name]) for name in names}
    material = tmp_path / "A07/review.md"
    material.write_text(artifacts["A07/review.md"], encoding="utf-8", newline="\n")
    hashes["A07/review.md"] = sha256(material.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    RunStore.write(manifest, {"artifact_sha256": hashes})
    review = artifacts["A07/review-template.json"]
    review.update(reviewer="Synthetic independent reviewer", review_id="SYNTHETIC-V2",
                  reviewed_at=datetime.now(timezone.utc).isoformat(), decision="approved")
    review["checklist"] = dict.fromkeys(review["checklist"], "pass")
    input_path = tmp_path / "review-input.json"
    RunStore.write(input_path, review)
    result = record_review(tmp_path, "A07", input_path, artifacts, summary)
    assert result["approved_candidate"] and not result["runtime_publication"]
    assert load_json(Path(result["review"]) / "review-source.json")["material_sha256"] == hashes["A07/review.md"]

    material.write_text("Changed example explanation", encoding="utf-8")
    hashes["A07/review.md"] = sha256(material.read_bytes()).hexdigest()
    manifest.write_text(json.dumps({"artifact_sha256": hashes}), encoding="utf-8")
    with pytest.raises(ValueError, match="annotated review material changed"):
        record_review(tmp_path, "A07", input_path, artifacts, summary)


def test_team_reviews_are_bound_to_pack_hash_and_hold_source_rights():
    batch = ROOT / "content/authoring/batches/a02-e02-oatutor.v2"
    source = load_json(ROOT / "docs/implementation/member2/part2/source-rights.json")
    assert len(source["items"]) == 8 and source["item_rights_passed"] == 0
    for concept in ("A02", "E02"):
        pack = ConceptPack.model_validate(load_json(batch / concept / "draft.json"))
        review = ContentReview.model_validate(
            load_json(batch / "reviews" / concept / "M2-TEAM-20261123" / "review.json")
        )
        assert review.pack_sha256 == digest(pack.model_dump(mode="json"))
        assert review.decision == "content_pass_source_pending"
        assert review.checklist.source_rights == "not_checked"
        assert not (batch / "reviews" / concept / review.review_id / "approved-pack.json").exists()


def test_original_pilot_review_checks_snapshot_and_only_writes_candidate(tmp_path):
    artifacts, summary = rendered_pilot()
    (tmp_path / "A07").mkdir()
    names = ("registry-snapshot.json", "A07/request.json", "A07/draft.json")
    hashes = {name: RunStore.write(tmp_path / name, artifacts[name]) for name in names}
    RunStore.write(tmp_path / "manifest.json", {"artifact_sha256": hashes})
    review = artifacts["A07/review-template.json"]
    review.update(reviewer="Synthetic independent reviewer", review_id="SYNTHETIC",
                  reviewed_at=datetime.now(timezone.utc).isoformat(), decision="approved")
    review["checklist"] = dict.fromkeys(review["checklist"], "pass")
    input_path = tmp_path / "review-input.json"
    RunStore.write(input_path, review)
    result = record_review(tmp_path, "A07", input_path, artifacts, summary)
    assert result["approved_candidate"] and not result["runtime_publication"]
    assert load_json(tmp_path / "A07/draft.json")["review"]["status"] == "draft"
    candidate = load_json(Path(result["review"]) / "approved-pack.json")
    assert candidate["review"]["status"] == "human_approved"


def test_gemini_sends_one_bounded_request_and_validates_the_full_pack(monkeypatch):
    monkeypatch.setenv("AUTHORING_LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    original = DraftRequest.model_validate(load_json(ROOT / "content/authoring/configs/a02.v1.json"))
    request = original.model_copy(update={"model": "gemini-3.1-flash-lite"})
    _, bank = load_curriculum()
    generated, _ = pilot_replay(original, bank)
    requests = []

    def respond(http_request):
        requests.append(http_request)
        assert http_request.url.host == "generativelanguage.googleapis.com"
        assert http_request.headers["x-goog-api-key"] == "synthetic-key"
        assert "synthetic-key" not in str(http_request.url)
        generation = json.loads(http_request.content)["generationConfig"]
        assert generation["maxOutputTokens"] == request.max_output_tokens
        assert generation["responseJsonSchema"]["properties"]["problems"]["type"] == "array"
        return httpx.Response(200, json={
            "modelVersion": "gemini-test-model", "responseId": "synthetic-response",
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": generated.model_dump_json()}]}}],
            "usageMetadata": {"totalTokenCount": 128},
        })

    factory = lambda **kwargs: httpx.Client(transport=httpx.MockTransport(respond), **kwargs)
    content, metadata = generate_gemini(request, [{"content": "rules"}, {"content": "context"}], factory)
    assert content == generated
    assert len(requests) == metadata["model_calls"] == 1
    assert metadata["usage"] == {"totalTokenCount": 128}
    assert "synthetic-key" not in json.dumps(metadata)
