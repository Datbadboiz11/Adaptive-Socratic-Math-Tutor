"""Export full API including opt-in authoring endpoints, preserving MVP snapshot."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
from app.main import app

target = ROOT/'contracts/pilot/openapi.json'
content = json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2)+'\n'
if '--check' in sys.argv:
    if not target.exists() or target.read_text(encoding='utf-8') != content:
        raise SystemExit('Run scripts/exports/export_pilot_openapi.py')
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
print('PASS: full pilot API snapshot matches implementation')
