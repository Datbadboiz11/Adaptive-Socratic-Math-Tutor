"""Read-only offline verification of pinned sources, draft batch and proposed dev qrels."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/authoring"))

from prepare_oatutor_batch import check_batch

if __name__ == "__main__":
    result = check_batch()
    print("PASS: pinned OATutor files, exact math, provenance, 24 proposed dev queries and draft publication boundary")
    print(json.dumps(result, ensure_ascii=True))
