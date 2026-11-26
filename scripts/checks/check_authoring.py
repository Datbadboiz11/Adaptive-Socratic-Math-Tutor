"""Read-only authoring config, schema, replay and publication-boundary checks."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.authoring_runs import (
    RunStore, authoring_prompt, check_run, check_source_draft, load_authoring_source, load_json, pilot_replay, verify_run,
)
from app.content_authoring import ContentReview, DraftRequest, GeneratedContent, make_draft
from app.curriculum import PilotBank, safe_chunks


def artifacts():
    return {ROOT / "contracts/authoring/v1" / (model.__name__ + ".schema.json"):
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
            for model in (DraftRequest, GeneratedContent, ContentReview)}


def audit(source="member2-v2"):
    registry, bank = load_authoring_source(source)
    summaries = []
    configs = (sorted((ROOT / "content/authoring/configs/member2-v2").glob("*.json")) if source == "member2-v2" else
               [ROOT / f"content/authoring/configs/{cid}.v1.json" for cid in ("a02", "e02")])
    if source == "member2-v2" and {path.stem for path in configs} != {pack.concept_id for pack in bank.packs}:
        raise ValueError("Provide one config for each of the 13 Member 2 concepts")
    for config in configs:
        request = DraftRequest.model_validate(load_json(config))
        concept = request.concept_id
        authoring_prompt(request, registry, source)
        content, metadata = pilot_replay(request, bank)
        pack = make_draft(content, request)
        result = check_source_draft(pack, request, registry, bank, source)
        if not result.passed:
            raise ValueError(result.model_dump_json())
        replaced = PilotBank.model_validate({**bank.model_dump(mode="json"),
            "packs": [pack.model_dump(mode="json") if p.concept_id == concept else p.model_dump(mode="json") for p in bank.packs]})
        if safe_chunks(registry, replaced, concept):
            raise ValueError("Draft content leaked through publication boundary")
        summaries.append({"concept_id": concept, "problems": len(pack.problems), "examples": len(pack.examples),
                          "error_fixtures": len(pack.errors), "check_passed": result.passed,
                          "review_status": pack.review.status, "provider": metadata["provider"], "model_calls": 0})
    return summaries


def audit_live(run_id):
    path = RunStore().path(run_id)
    manifest = verify_run(path)
    request = DraftRequest.model_validate(load_json(path / "request.json"))
    _, bank = load_authoring_source("member2-v2")
    generation = manifest["generation"]
    if (manifest["status"] != "draft_ready" or manifest.get("source") != "member2-v2"
            or generation["provider"] not in ("openai", "gemini") or generation.get("model_calls") != 1
            or not generation.get("usage") or request.concept_id not in {pack.concept_id for pack in bank.packs}
            or not check_run(path).passed):
        raise ValueError("A live acceptance run must generate a valid Member 2 draft through the provider")
    pack = load_json(path / "draft.json")
    if pack["review"]["status"] != "draft" or manifest["human_review"] != "pending":
        raise ValueError("Live model generation must retain pending human review")
    return {"run_id": run_id, "concept_id": request.concept_id, "source": manifest["source"],
            "prompt_version": manifest["prompt_version"], "provider": generation["provider"],
            "model_requested": generation["model_requested"], "model_returned": generation["model_returned"],
            "usage": generation["usage"], "model_calls": generation["model_calls"],
            "check_passed": True, "review_status": "draft"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", choices=["DraftRequest", "GeneratedContent", "ContentReview"])
    parser.add_argument("--source", choices=("legacy", "member2-v2"), default="member2-v2")
    parser.add_argument("--live-run", help="Verify a saved real-provider run without making an API call")
    args = parser.parse_args()
    expected = artifacts()
    if args.render:
        print(next(content for path, content in expected.items() if path.stem == args.render + ".schema"), end="")
        return
    for path, content in expected.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit("Stale authoring schema: " + str(path.relative_to(ROOT)))
    result = audit(args.source)
    live = audit_live(args.live_run) if args.live_run else None
    print(f"PASS: authoring schemas, {len(result)} offline pilot replays and draft publication boundary")
    print(json.dumps({"offline": result, "live": live} if live else result, ensure_ascii=True))


if __name__ == "__main__":
    main()
