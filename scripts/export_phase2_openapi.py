"""Version the implemented API separately from the Phase 1 target contracts."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.main import app

parser = argparse.ArgumentParser()
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
target = ROOT / 'contracts/phase2/openapi.json'
expected = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + '\n'
if args.check:
    if not target.exists() or target.read_text(encoding='utf-8') != expected:
        raise SystemExit('OpenAPI differs: run python scripts/export_phase2_openapi.py')
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(expected, encoding='utf-8')
print('PASS: Phase 2 OpenAPI matches implementation')
