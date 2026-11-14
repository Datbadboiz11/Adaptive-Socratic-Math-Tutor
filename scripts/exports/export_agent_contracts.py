"""Xuất JSON Schema các hợp đồng của Member 3 (Agent, LLM extraction) từ Pydantic.

    python scripts/exports/export_agent_contracts.py          # ghi file
    python scripts/exports/export_agent_contracts.py --check  # báo lỗi nếu schema cũ
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent.decision import EXPORTED_MODELS as AGENT_MODELS  # noqa: E402
from app.agent.graph import TurnInput, TutorReply  # noqa: E402
from app.agent.tools import TurnContext  # noqa: E402
from app.extraction.contracts import EXPORTED_MODELS as EXTRACTION_MODELS  # noqa: E402

TARGETS = {
    "contracts/agent": (*AGENT_MODELS, TurnContext, TurnInput, TutorReply),
    "contracts/extraction": EXTRACTION_MODELS,
}

count = 0
for folder, models in TARGETS.items():
    for model in models:
        target = ROOT / folder / f"{model.__name__}.schema.json"
        content = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
        if "--check" in sys.argv:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Stale schema: {folder}/{target.name}; run scripts/exports/export_agent_contracts.py")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        count += 1
print(f"PASS: {count} contract schemas (agent, extraction)")
