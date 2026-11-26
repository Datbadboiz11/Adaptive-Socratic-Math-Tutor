"""Collect the initial Stage 4 delivery/report acceptance with evidence hashes."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-run',required=True)
    parser.add_argument('--tests-xml',type=Path,default=ROOT/'artifacts/validation-db-tests.xml')
    args=parser.parse_args()
    if not re.fullmatch('[0-9a-f]{12}',args.browser_run): parser.error('Invalid browser run')
    browser_path=ROOT/'artifacts/browser-validation'/('stage4-'+args.browser_run)/'verification.json'
    browser=json.loads(browser_path.read_text(encoding='utf-8'))
    if browser['browser_errors'] or not browser['schema_removed'] or browser['model_api_calls']!=0:
        raise ValueError('Browser acceptance is incomplete')
    suite=ET.parse(args.tests_xml).getroot().find('testsuite')
    counts={key:int(suite.attrib.get(key,0)) for key in ('tests','failures','errors','skipped')}
    if counts['failures'] or counts['errors'] or counts['skipped']: raise ValueError('Full DB tests must pass without skips')
    checks=[]
    for command in ('scripts/exports/export_frontend_types.py --check',
                    'scripts/exports/export_phase3_openapi.py --check',
                    'scripts/exports/export_contracts.py --check',
                    'scripts/checks/check_stage3_kb.py'):
        result=subprocess.run([sys.executable,*command.split()],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
        if result.returncode: raise RuntimeError('Check failed: '+command)
        checks.append({'command':command,'exit_code':0,'stdout_sha256':hashlib.sha256(result.stdout.encode()).hexdigest()})
    out=ROOT/'docs/implementation/member2/part4'
    out.mkdir(parents=True,exist_ok=True)
    test_out=out/'tests-stage4-2026-11-26.xml'
    browser_out=out/'browser-stage4-2026-11-26.json'
    test_out.write_bytes(args.tests_xml.read_bytes())
    browser_out.write_bytes(browser_path.read_bytes())
    sources=['backend/migrations/004_teaching_delivery.sql','backend/app/main.py','backend/app/teaching_runtime.py','backend/app/tutor.py',
        'backend/app/tutor_service.py','backend/app/sessions.py','backend/app/session_contracts.py',
        'frontend/app/workspace.tsx','frontend/app/lib/api.ts','frontend/app/lib/api-types.ts',
        'frontend/app/components/MathText.tsx','frontend/app/components/TeachingFeedback.tsx',
        'frontend/app/components/SkillEvidence.tsx','scripts/exports/export_frontend_types.py',
        'scripts/checks/check_stage4_browser.py','tests/test_stage4_teaching.py','tests/test_phase3_db.py',
        '.github/workflows/repository-checks.yml','.env.example','compose.yaml']
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'stage':'Member 2 Chặng 4',
        'status':'initial_grounded_delivery_slice_verified','pytest':counts,'browser':browser,
        'checks':checks,'model_api_calls':0,'public_api_version':'0.4.0',
        'frontend_build_and_typecheck':'passed_before_browser_acceptance',
        'implemented':['canonical session pins Full/No-RAG and KB snapshot','retrieved/generator/delivered refs separated',
            'direct/metadata KB node outside session transaction','verbatim reviewed content assembler and exact guard',
            'atomic delivery/assistance including level zero','durable replay and withdrawal recheck',
            'per-skill evidence and immutable finished report','generated public TS types and extracted feedback/report components',
            'safe native MathML subset and escaped text fallback'],
        'remaining':['free-form LLM grounded generation and independent quality review',
            'graph navigation and evidence-based prerequisite recommendations',
            'richer diagnosis UI, mixed-skill sessions and full mathematical layout',
            'independent member review, Docker/remote CI and formal Full/No-RAG RQ3'],
        'source_sha256':{name:sha(ROOT/name) for name in sources},
        'evidence_sha256':{test_out.name:sha(test_out),browser_out.name:sha(browser_out)}}
    destination=out/'verification-stage4-2026-11-26.json'
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','tests':counts['tests'],'browser_checks':len(browser['checks']),
                      'evidence':str(destination.relative_to(ROOT))}))


if __name__=='__main__': main()
