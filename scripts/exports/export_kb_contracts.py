"""Versioned Stage 3 schemas. KBScope/KBRequest are internal; tool input is RetrievalQuery only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "backend"))
from app.kb_contracts import EmbeddingProfile,ExamplePublication,KBChunk,KBRequest,KBResult,KBScope
from app.member2_contracts import RetrievalQuery


def audit(check=False):
    paths = []
    for model in (EmbeddingProfile,ExamplePublication,KBChunk,KBRequest,KBResult,KBScope,RetrievalQuery):
        path = ROOT / "contracts/kb/v1" / (model.__name__ + ".schema.json")
        expected = json.dumps(model.model_json_schema(),ensure_ascii=False,indent=2) + "\n"
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                raise ValueError("Missing or stale KB schema: " + model.__name__)
        else:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(expected,encoding="utf-8")
        paths.append(str(path.relative_to(ROOT)))
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    args = parser.parse_args()
    print(json.dumps({"schemas":len(audit(args.check)),"tool_input":"RetrievalQuery","scope":"server_only"}))
