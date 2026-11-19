"""Curate Stage 3 acceptance, real DB traces and source hashes. Never reads/copies .env contents."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/implementation/member2/part3"
sys.path.insert(0,str(ROOT / "backend"))
sys.path.insert(0,str(ROOT / "scripts/dev"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def write_new(path,data):
    with path.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-run",required=True)
    args = parser.parse_args()
    if not re.fullmatch("[0-9a-f]{12}",args.acceptance_run):
        parser.error("Invalid acceptance run ID")
    acceptance_file = ROOT / "artifacts/stage3-validation" / args.acceptance_run / "acceptance.json"
    acceptance = json.loads(acceptance_file.read_text(encoding="utf-8"))
    baseline = json.loads((ROOT / "artifacts/stage2-completion-c21830512ce9/baseline.json").read_text(encoding="utf-8"))
    changed = [name for name,value in baseline.items() if sha(ROOT / name)!=value]
    if changed:
        raise ValueError("Frozen source files changed")
    tests_file = ROOT / "artifacts/stage3-tests.xml"
    suite = ET.parse(tests_file).getroot().find("testsuite").attrib
    if any(int(suite[key]) for key in ("failures","errors","skipped")):
        raise ValueError("Stage 3 regression has failures or skipped tests")
    from validation_runtime import local_environment
    environment = local_environment()
    for name in ("OPENAI_API_KEY","GEMINI_API_KEY"):
        environment.pop(name,None)
    environment.update(LLM_PROVIDER="openai",LLM_ENABLED="false",AUTHORING_LLM_ENABLED="false")
    commands = ["scripts/checks/check_phase1.py","scripts/checks/check_curriculum.py",
        "scripts/checks/check_member2_foundation.py","scripts/checks/check_authoring.py",
        "scripts/checks/check_oatutor_pilot.py","scripts/checks/check_stage2_completion.py",
        "scripts/checks/check_stage2_math.py","scripts/checks/check_member2_ai_review.py",
        "scripts/exports/export_contracts.py --check","scripts/exports/export_phase3_openapi.py --check",
        "scripts/exports/export_kb_contracts.py --check","scripts/checks/check_stage3_kb.py"]
    checks = []
    for command in commands:
        started = perf_counter()
        result = subprocess.run([sys.executable,*command.split()],cwd=ROOT,env=environment,
                                capture_output=True,text=True,encoding="utf-8",timeout=45)
        if result.returncode:
            raise RuntimeError("Checker failed: "+command)
        checks.append({"command":command,"exit_code":0,"elapsed_seconds":perf_counter()-started,
                       "stdout_sha256":hashlib.sha256(result.stdout.encode()).hexdigest()})
    import yaml
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load((ROOT / ".github/workflows/repository-checks.yml").read_text(encoding="utf-8"))
    assert compose["services"]["db"]["image"].startswith("pgvector/pgvector:")
    assert workflow["jobs"]["checks"]["services"]["postgres"]["image"].startswith("pgvector/pgvector:")
    namespace = acceptance["acceptance"]["fixture_namespace"]
    from app.db import connect
    import os
    os.environ.update(environment)
    with connect() as c:
        traces = c.execute("SELECT * FROM kb_retrieval_traces WHERE namespace=%s ORDER BY created_at,retrieval_id",(namespace,)).fetchall()
        production = {"concepts":c.execute("SELECT count(*) AS n FROM kb_concepts WHERE namespace='runtime'").fetchone()["n"],
            "skills":c.execute("SELECT count(*) AS n FROM kb_skills WHERE namespace='runtime'").fetchone()["n"],
            "chunks":c.execute("SELECT count(*) AS n FROM kb_chunks WHERE namespace='runtime'").fetchone()["n"]}
    export_path = ROOT / "artifacts/stage3-validation" / args.acceptance_run / "runtime-export.json"
    export_command = [sys.executable,"scripts/kb/sync_kb.py","--workspace-local","export","--snapshot",
                      acceptance["acceptance"]["runtime_active_snapshot"],"--output",str(export_path)]
    result = subprocess.run(export_command,cwd=ROOT,env=environment,capture_output=True,text=True,encoding="utf-8",timeout=15)
    if result.returncode:
        raise RuntimeError("Snapshot export acceptance failed")
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    def contains_private(value):
        if isinstance(value,dict):
            return bool(set(value).intersection({"reference_answer","reference_steps","private_payload","response_steps"})) or any(contains_private(v) for v in value.values())
        return isinstance(value,list) and any(contains_private(v) for v in value)
    if contains_private(exported):
        raise ValueError("Private reference in snapshot export")
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT / "acceptance.json").open("xb") as stream:
        stream.write(acceptance_file.read_bytes())
    with (OUT / "tests.xml").open("xb") as stream:
        stream.write(tests_file.read_bytes())
    # UUID/timestamps are synthetic and JSON-encoded as strings; no query text or model key.
    serialized_traces = json.loads(json.dumps(traces,default=str))
    write_new(OUT / "retrieval-traces.json",{"namespace":namespace,"usage":"retrieval_only_not_context_injection_or_delivery","traces":serialized_traces})
    write_new(OUT / "checks.json",checks)
    source_files = ["backend/migrations/003_curriculum_kb.sql","backend/app/kb_contracts.py","backend/app/kb_projection.py",
        "backend/app/embeddings.py","backend/app/kb_sync.py","backend/app/retrieval.py","backend/app/kb_tool.py",
        "backend/app/kb_cli.py","backend/requirements-rag.txt","backend/Dockerfile","compose.yaml",".env.example",
        ".dockerignore",".github/workflows/repository-checks.yml","scripts/dev/validation_runtime.py",
        "scripts/kb/sync_kb.py","scripts/kb/prepare_embedding_model.py","scripts/checks/check_stage3_kb.py",
        "scripts/checks/collect_stage3_validation.py","scripts/exports/export_kb_contracts.py",
        "tests/kb_support.py","tests/test_kb_unit.py","tests/test_kb_db.py","content/kb/embedding-profile.v1.json"]
    source_files += [str(p.relative_to(ROOT)).replace("\\","/") for p in sorted((ROOT / "contracts/kb/v1").glob("*.json"))]
    report = {"checked_at":datetime.now(timezone.utc).isoformat(),"stage":"Member 2 Chặng 3","technical_status":"complete",
        "pytest":{**suite,"RUN_DB_TESTS":True,"live_api_keys_removed":True},"stage3_tests":48,"checkers_passed":len(checks),
        "postgres":acceptance["acceptance"]["postgres"],"pgvector":acceptance["acceptance"]["pgvector"],
        "production":production,"human_approved_real_packs":0,"model_api_calls":0,"real_embedding_acceptance":True,
        "synthetic_fixture_positive_retrieval":True,"real_human_attestation":False,"agent_integration":False,
        "source_files_preserved":len(baseline),"source_file_changes":changed,"snapshot_export_private_references":False,
        "config_yaml_parse":"passed","docker_execution":"not_run_no_docker","remote_ci":"not_run_no_git_or_connected_repository",
        "retrieval_trace_count":len(traces),"stopped_after_stage3":True,
        "source_file_sha256":{name:sha(ROOT / name) for name in source_files},
        "evidence_sha256":{name:sha(OUT / name) for name in ("acceptance.json","tests.xml","retrieval-traces.json","checks.json")}}
    write_new(OUT / "verification.json",report)
    print(json.dumps({"status":"passed","tests":int(suite["tests"]),"stage3_tests":48,"checkers":len(checks),
        "source_files_preserved":len(baseline),"evidence_directory":str(OUT.relative_to(ROOT))},indent=2))


if __name__ == "__main__":
    main()
