"""Check legacy MVP API; the additive pilot API has a separate snapshot."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.main import app
parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
path=ROOT/'contracts/phase3/openapi.json'
document=deepcopy(app.openapi())
document['paths']={k:v for k,v in document['paths'].items() if not k.startswith('/api/v1/pilot/')}
def references(value):
    if isinstance(value,dict):
        if '$ref' in value: yield value['$ref'].rsplit('/',1)[-1]
        for child in value.values(): yield from references(child)
    elif isinstance(value,list):
        for child in value: yield from references(child)
schemas=document['components']['schemas']
needed=set(references(document['paths'])); pending=list(needed)
while pending:
    for name in references(schemas[pending.pop()]):
        if name not in needed: needed.add(name); pending.append(name)
document['components']['schemas']={k:v for k,v in schemas.items() if k in needed}
expected=json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
if args.check:
    if not path.exists() or path.read_text(encoding='utf-8')!=expected: raise SystemExit('Run scripts/exports/export_phase3_openapi.py')
else:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(expected,encoding='utf-8')
print('PASS: Phase 3 OpenAPI matches implementation')
