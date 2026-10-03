"""Export reviewable JSON Schemas from the canonical Pydantic contracts."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import contracts  # noqa: E402

MODELS = [
    contracts.ProblemPublic, contracts.ContentBank, contracts.CreateSession,
    contracts.SessionPublic, contracts.DraftRequest, contracts.TurnRequest,
    contracts.Assessment, contracts.Opportunity, contracts.Eligibility,
    contracts.Observation, contracts.TutorResponse, contracts.SessionReport,
    contracts.ErrorResponse,
]

for model in MODELS:
    target = ROOT / "contracts/v1" / f"{model.__name__}.schema.json"
    content = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Stale schema: {target.name}; run scripts/exports/export_contracts.py")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
print(f"PASS: {len(MODELS)} contract schemas")
