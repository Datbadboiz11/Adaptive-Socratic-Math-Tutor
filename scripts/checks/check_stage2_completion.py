"""Offline verification of stage 2 revision, review schemas and separate publication gates."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/authoring"))

from app.authoring_reviews import CurriculumReview, LabelsReview
from app.oatutor_import import require
from prepare_oatutor_batch import BATCH_ROOT_V2, check_batch


def schema_artifacts():
    return {ROOT / "contracts/authoring/review-v1" / (model.__name__ + ".schema.json"):
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
            for model in (CurriculumReview, LabelsReview)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-schemas", action="store_true", help="Create missing schemas only; never overwrite")
    args = parser.parse_args()
    for path, content in schema_artifacts().items():
        if args.write_schemas and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
        require(path.exists() and path.read_text(encoding="utf-8") == content, "Missing or stale review schema: " + str(path))
    result = check_batch(BATCH_ROOT_V2)
    print("PASS: stage 2 revision, A02/A07 separation, exact mathematics, UTF-8 inputs, proposed labels and review schemas")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
