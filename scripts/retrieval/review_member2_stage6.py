"""Compare two independent ratings of the blinded Stage 6 packet without modifying source artifacts."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from research.retrieval.dataset import json_bytes, sha256, write_new_bundle
from research.retrieval.stage6.ratings import compare_reviews, load_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        packet, key, _ = load_run(args.run)
        reviews = [json.loads(path.read_text(encoding="utf-8")) for path in (args.first, args.second)]
        report = compare_reviews(*reviews, packet, key)
        report["review_files_sha256"] = {label: sha256(path.read_bytes())
                                         for label, path in (("first", args.first), ("second", args.second))}
        write_new_bundle(args.output.parent, {args.output.name: json_bytes(report)})
        print(json.dumps({"status": report["status"], "output": str(args.output), "formal_test_ready": False}))
        return 2 if report["conflicts"] else 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, "Stage 6 rating failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
