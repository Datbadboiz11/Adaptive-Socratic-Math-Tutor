"""Read-only authoring config, schema, replay and publication-boundary checks."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.authoring_runs import TEMPLATE, load_json, pilot_replay
from app.content_authoring import ContentReview, DraftRequest, GeneratedContent, build_prompt, check_draft, make_draft
from app.curriculum import PilotBank, load_curriculum, safe_chunks


def artifacts():
    return {ROOT / "contracts/authoring/v1" / (model.__name__ + ".schema.json"):
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
            for model in (DraftRequest, GeneratedContent, ContentReview)}


def audit():
    registry, bank = load_curriculum()
    summaries = []
    for concept in ("A02", "E02"):
        request = DraftRequest.model_validate(load_json(ROOT / f"content/authoring/configs/{concept.lower()}.v1.json"))
        build_prompt(request, registry, TEMPLATE.read_text(encoding="utf-8"))
        content, metadata = pilot_replay(request, bank)
        pack = make_draft(content, request)
        result = check_draft(pack, request, registry, bank)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", choices=["DraftRequest", "GeneratedContent", "ContentReview"])
    args = parser.parse_args()
    expected = artifacts()
    if args.render:
        print(next(content for path, content in expected.items() if path.stem == args.render + ".schema"), end="")
        return
    for path, content in expected.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit("Stale authoring schema: " + str(path.relative_to(ROOT)))
    print("PASS: authoring schemas, two offline pilot replays and draft publication boundary")
    print(json.dumps(audit(), ensure_ascii=True))


if __name__ == "__main__":
    main()
