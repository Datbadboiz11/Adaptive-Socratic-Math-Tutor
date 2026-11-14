"""Xuất JSON Schema của hợp đồng Agent (Member 3) từ Pydantic.

    python scripts/exports/export_agent_contracts.py          # ghi file
    python scripts/exports/export_agent_contracts.py --check  # báo lỗi nếu schema cũ
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent.decision import EXPORTED_MODELS  # noqa: E402
from app.agent.graph import TurnInput, TutorReply  # noqa: E402
from app.agent.tools import TurnContext  # noqa: E402

MODELS = (*EXPORTED_MODELS, TurnContext, TurnInput, TutorReply)

for model in MODELS:
    target = ROOT / "contracts/agent" / f"{model.__name__}.schema.json"
    content = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            raise SystemExit(f"Stale schema: {target.name}; run scripts/exports/export_agent_contracts.py")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
print(f"PASS: {len(MODELS)} agent contract schemas")
