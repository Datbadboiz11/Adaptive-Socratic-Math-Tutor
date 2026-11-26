"""Collect current Stage 4 acceptance, its scope and source/evidence hashes."""
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
    parser.add_argument('--tests-xml',type=Path,default=ROOT/'artifacts/stage4-current-tests.xml')
    parser.add_argument('--suite-scope',choices=['full','stage4_and_runtime'],default='stage4_and_runtime')
    args=parser.parse_args()
    if not re.fullmatch('[0-9a-f]{12}',args.browser_run): parser.error('Invalid browser run')
    browser_path=ROOT/'artifacts/browser-validation'/('stage4-'+args.browser_run)/'verification.json'
    browser=json.loads(browser_path.read_text(encoding='utf-8'))
    if (browser['browser_errors'] or not browser['schema_removed'] or browser['model_api_calls']!=0
            or not browser.get('real_local_embeddings') or not browser.get('schema_isolated')
            or len(browser['checks']) < 10 or any(c['status']!='passed' for c in browser['checks'])):
        raise ValueError('Browser acceptance is incomplete')
    suite=ET.parse(args.tests_xml).getroot().find('testsuite')
    counts={key:int(suite.attrib.get(key,0)) for key in ('tests','failures','errors','skipped')}
    if not counts['tests'] or counts['failures'] or counts['errors'] or counts['skipped']:
        raise ValueError('Selected DB tests must pass without skips')
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
    frontend_out=out/'tests-frontend-stage4-2026-11-26.xml'
    frontend=subprocess.run(['node','--experimental-strip-types','--test','--test-reporter=junit','tests/math-layout.test.mjs'],
        cwd=ROOT/'frontend',capture_output=True,text=True,encoding='utf-8',timeout=60)
    if frontend.returncode: raise RuntimeError('Frontend math layout tests failed')
    # Node 22 emits testcase children directly, without aggregate attributes.
    frontend_xml=ET.fromstring(frontend.stdout)
    frontend_counts={'tests':len(frontend_xml.findall('.//testcase')),
        **{key:len(frontend_xml.findall('.//'+tag)) for key,tag in
           (('failures','failure'),('errors','error'),('skipped','skipped'))}}
    if frontend_counts['tests'] < 4 or any(frontend_counts[k] for k in ('failures','errors','skipped')):
        raise ValueError('Frontend test evidence is incomplete')
    frontend_out.write_text(frontend.stdout,encoding='utf-8')
    test_out.write_bytes(args.tests_xml.read_bytes())
    browser_out.write_bytes(browser_path.read_bytes())
    sources=['backend/migrations/004_teaching_delivery.sql','backend/app/main.py','backend/app/teaching_runtime.py','backend/app/tutor.py',
        'backend/app/tutor_service.py','backend/app/sessions.py','backend/app/session_contracts.py',
        'backend/app/report_diagnoses.py',
        'frontend/app/workspace.tsx','frontend/app/workspace.css','frontend/app/lib/api.ts','frontend/app/lib/api-types.ts',
        'frontend/app/hooks/useTutorSession.ts','frontend/app/lib/math-layout.ts','frontend/tests/math-layout.test.mjs',
        'frontend/app/components/ProblemFormula.tsx','frontend/app/components/LearningReport.tsx','frontend/package.json',
        'frontend/app/components/MathText.tsx','frontend/app/components/TeachingFeedback.tsx',
        'frontend/app/components/SkillEvidence.tsx','scripts/exports/export_frontend_types.py',
        'scripts/checks/check_stage4_browser.py','tests/test_stage4_teaching.py','tests/test_phase3_db.py',
        'scripts/checks/check_stage3_kb.py','scripts/checks/collect_stage4_validation.py','tests/test_stage4_reports.py',
        '.github/workflows/stage4-current-checks.yml','docs/implementation/member2/part4/independent-review.md',
        'docs/implementation/member2/part4/README.md','docs/planning/member-2-plan.md',
        'scripts/dev/validation_runtime.py','contracts/phase3/openapi.json']
    optional_config=['.github/workflows/repository-checks.yml','.env.example','compose.yaml']
    missing_config=[name for name in optional_config if not (ROOT/name).is_file()]
    sources.extend(name for name in optional_config if name not in missing_config)
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'stage':'Member 2 Chặng 4',
        'status':'requested_stage4_gaps_verified_pending_independent_review','pytest':counts,'frontend_tests':frontend_counts,'browser':browser,
        'suite_scope':args.suite_scope,
        'historical_suite_limit':'Historical A02/E02 source batches are absent in the current workspace; archived tests requiring them are not part of the current scoped acceptance.',
        'configuration_files_unavailable':missing_config,
        'checks':checks,'model_api_calls':0,'public_api_version':'0.4.0',
        'frontend_build_and_typecheck':'passed_before_browser_acceptance',
        'implemented':['canonical session pins Full/No-RAG and KB snapshot','retrieved/generator/delivered refs separated',
            'direct/metadata KB node outside session transaction','verbatim reviewed content assembler and exact guard',
            'atomic delivery/assistance including level zero','durable replay and withdrawal recheck',
            'per-skill evidence and immutable finished report','generated public TS types and extracted feedback/report components',
            'bounded native MathML: nested fractions, exponents, roots and equation systems; escaped fallback',
            'session/request hook preserving replay IDs, draft, conflict and profile isolation',
            'diagnoses with suspected/supported/rejected status, narrow evidence scope and report turn anchors',
            'BKT version/source/time display and honest unavailable provenance for unknown versions',
            'keyboard/focus including first submission and actual AbortController timeout via virtual time',
            'independent reviewer handoff and scoped current-release CI configuration'],
        'remaining':['independent Member 1/3 sign-off and remote CI/Docker execution evidence'],
        'separate_scope':['free-form LLM generation','graph prerequisite navigation','mixed-skill session authoring',
                          'formal Full/No-RAG RQ3','mathematical notation beyond the declared presentation grammar'],
        'source_sha256':{name:sha(ROOT/name) for name in sources},
        'evidence_sha256':{test_out.name:sha(test_out),browser_out.name:sha(browser_out),frontend_out.name:sha(frontend_out)}}
    destination=out/'verification-stage4-2026-11-26.json'
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','tests':counts['tests'],'browser_checks':len(browser['checks']),
                      'evidence':str(destination.relative_to(ROOT))}))


if __name__=='__main__': main()
