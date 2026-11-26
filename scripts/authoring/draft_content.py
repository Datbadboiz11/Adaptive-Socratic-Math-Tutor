"""Author one concept per run, inspect checks, and record a real independent review."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import ValidationError
from app.authoring_runs import (
    RunStore, authoring_prompt, check_run, create_run, load_authoring_source, load_json, review_run, safe_validation_errors,
)
from app.content_authoring import ContentReview, DraftRequest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Print prompt/config without generation or file writes")
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--source", choices=("legacy", "member2-v2"), default="legacy")
    plan.add_argument("--model", help="Override the model ID and record it in the run request")
    draft = commands.add_parser("draft", help="Create a new immutable draft run")
    draft.add_argument("--config", type=Path, required=True)
    draft.add_argument("--run-id", required=True)
    draft.add_argument("--provider", choices=["openai", "gemini", "replay", "pilot_replay"], required=True)
    draft.add_argument("--input", type=Path)
    draft.add_argument("--source", choices=("legacy", "member2-v2"), default="legacy")
    draft.add_argument("--model", help="Override the model ID and record it in the run request")
    check = commands.add_parser("check", help="Verify artifacts and recheck a run")
    check.add_argument("--run-id", required=True)
    review = commands.add_parser("review", help="Record a completed independent human review")
    review.add_argument("--run-id", required=True)
    review.add_argument("--review-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command in ("plan", "draft"):
            request = DraftRequest.model_validate(load_json(args.config))
            if args.model:
                request = DraftRequest.model_validate({**request.model_dump(), "model": args.model})
            if args.command == "plan":
                registry, _ = load_authoring_source(args.source)
                print(json.dumps(authoring_prompt(request, registry, args.source), ensure_ascii=True, indent=2))
                return 0
            if args.provider == "replay" and args.input is None:
                parser.error("--input is required with --provider replay")
            if args.provider != "replay" and args.input is not None:
                parser.error("--input is only valid with --provider replay")
            path, manifest = create_run(request, args.run_id, args.provider, input_path=args.input, source=args.source)
            print(json.dumps({"run": str(path), "status": manifest["status"], "generation": manifest["generation"]}, ensure_ascii=True))
            return 0 if manifest["status"] == "draft_ready" else 2
        if args.command == "check":
            path = RunStore().path(args.run_id)
            result = check_run(path)
            print(json.dumps({**result.model_dump(mode="json"), "passed": result.passed}, ensure_ascii=True, indent=2))
            return 0 if result.passed else 2
        result = ContentReview.model_validate(load_json(args.review_file))
        path, approved = review_run(args.run_id, result)
        print(json.dumps({"review": str(path), "approved_candidate": approved, "runtime_publication": False}))
        return 0
    except ValidationError as error:
        print(json.dumps({"status": "invalid_input", "issues": safe_validation_errors(error)}, ensure_ascii=True), file=sys.stderr)
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "failed", "type": type(error).__name__,
                          "message": "Check config/run files. Existing runs are immutable; use a new run ID."}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
