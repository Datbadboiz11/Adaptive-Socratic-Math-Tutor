"""Export current API separately; Phase 2 OpenAPI is a historical contract."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.main import app
parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
path=ROOT/'contracts/phase3/openapi.json'
expected=json.dumps(app.openapi(),ensure_ascii=False,sort_keys=True,indent=2)+'\n'
if args.check:
    if not path.exists() or path.read_text(encoding='utf-8')!=expected: raise SystemExit('Run scripts/export_phase3_openapi.py')
else:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(expected,encoding='utf-8')
print('PASS: Phase 3 OpenAPI matches implementation')
