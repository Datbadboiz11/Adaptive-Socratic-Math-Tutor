"""Inspect an unjudged Stage 5 dataset and collect two independent, version-pinned reviews."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from research.retrieval.dataset import (
    compare_reviews, json_bytes, review_template, sha256, validate_bundle, write_new_bundle,
)

DEFAULT = ROOT / "research/retrieval/stage5/member2-13.v1"


def readiness(manifest, queries):
    missing = sorted({q["concept_id"] for q in queries if q["content_status"] != "ready"})
    return {"dataset_id": manifest["dataset_id"], "status": manifest["status"],
            "owner": manifest.get("owner"), "concept_count": manifest["concept_count"],
            "query_count": len(queries), "unjudged_candidates": manifest["judgment_count"],
            "pilot_queries": len(manifest["pilot_query_ids"]),
            "concepts_awaiting_reviewed_content": missing, "formal_test_ready": False,
            "other_members_block_current_scope": manifest.get("other_members_block_current_scope"),
            "freeze_blockers": manifest.get("completion_requirements", [
                *(["content_and_scope_review"] if missing else []), "independent_query_and_label_reviews",
                "resolve_label_disagreements", "pin_embedding_and_retrieval_config",
                "freeze_all_final_test_inputs_before_evaluation"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Check source/file hashes, scope, versions and split isolation")
    template = commands.add_parser("template", help="Create a new review file without modifying the dataset")
    template.add_argument("--selection", choices=("pilot", "full", "ready", "dev", "test_candidate"), default="pilot")
    template.add_argument("--slot", choices=("A", "B"), required=True)
    template.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare", help="Validate independently completed reviews; retain disagreements")
    compare.add_argument("--first", type=Path, required=True)
    compare.add_argument("--second", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest, _, queries, qrels = validate_bundle(args.dataset, ROOT)
        if args.command == "check":
            print(json.dumps(readiness(manifest, queries), ensure_ascii=True, indent=2))
            return 0
        if args.command == "template":
            query_ids = manifest["pilot_query_ids"] if args.selection == "pilot" else [
                q["query_id"] for q in queries if args.selection == "full" or
                (q["content_status"] == "ready" if args.selection == "ready" else q["split"] == args.selection)]
            result = review_template(manifest["dataset_id"], manifest["files_sha256"]["corpus.json"],
                                     manifest["files_sha256"]["queries.json"], queries, qrels, query_ids, args.slot)
        else:
            read = lambda path: json.loads(path.read_text(encoding="utf-8"))
            result = compare_reviews(read(args.first), read(args.second), manifest, queries, qrels)
            result["review_files_sha256"] = {"first": sha256(args.first.read_bytes()),
                                              "second": sha256(args.second.read_bytes())}
        write_new_bundle(args.output.parent, {args.output.name: json_bytes(result)})
        print(json.dumps({"output": str(args.output), "status": result.get("status", "pending_review"),
                          "formal_test_ready": False}))
        return 2 if result.get("conflicts") else 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, "Stage 5 curation failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
