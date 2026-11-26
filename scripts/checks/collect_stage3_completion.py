"""Collect current Stage 3 handoff evidence without mutating the runtime KB."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from time import perf_counter
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/implementation/member2/part3"
for path in (ROOT / "backend", ROOT / "scripts/dev"):
    sys.path.insert(0, str(path))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-run", required=True)
    parser.add_argument("--tests-xml", type=Path, required=True)
    parser.add_argument("--frontend", action="store_true", help="Run and record frontend typecheck/build")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{12}", args.acceptance_run):
        parser.error("Invalid acceptance run ID")
    acceptance_path = ROOT / "artifacts/stage3-validation" / args.acceptance_run / "acceptance.json"
    tests_path = args.tests_xml.resolve()
    if not acceptance_path.is_file() or not tests_path.is_file():
        parser.error("Acceptance or test evidence is missing")
    evidence = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance = evidence["acceptance"]
    if (acceptance["real_runtime_approved_packs"] != 13
            or acceptance["real_runtime_approved_chunks"] != 91
            or acceptance["published_examples"] != 39
            or not acceptance["isolated_schema_fresh"]
            or not acceptance.get("isolation",{}).get("schema_removed")
            or acceptance["isolation"]["serving_before"] != acceptance["isolation"]["serving_after"]
            or any(summary["fallback_count"] != 13 for summary in acceptance["dev_summary"].values())):
        raise ValueError("Acceptance does not prove the completed 13-concept scope")

    root = ET.parse(tests_path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    test_summary = {key: int(float(suite.attrib.get(key, 0))) for key in ("tests", "failures", "errors", "skipped")}
    if test_summary["failures"] or test_summary["errors"] or test_summary["skipped"]:
        raise ValueError("Current full DB test run must have no failures or skips")

    from validation_runtime import local_environment
    environment = local_environment()
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        environment.pop(name, None)
    environment.update(LLM_PROVIDER="openai", LLM_ENABLED="false", AUTHORING_LLM_ENABLED="false")
    commands = [
        "scripts/kb/build_member2_stage3_assets.py --check",
        "scripts/checks/check_phase1.py", "scripts/checks/check_curriculum.py",
        "scripts/checks/check_member2_foundation.py", "scripts/checks/check_authoring.py",
        "scripts/checks/check_oatutor_pilot.py", "scripts/checks/check_stage2_completion.py",
        "scripts/checks/check_stage2_math.py", "scripts/checks/check_member2_ai_review.py",
        "scripts/exports/export_contracts.py --check", "scripts/exports/export_phase3_openapi.py --check",
        "scripts/exports/export_kb_contracts.py --check", "scripts/checks/check_stage3_kb.py",
    ]
    checks = []
    for command in commands:
        started = perf_counter()
        result = subprocess.run([sys.executable, *command.split()], cwd=ROOT, env=environment,
                                capture_output=True, text=True, encoding="utf-8", timeout=120)
        if result.returncode:
            raise RuntimeError("Checker failed: " + command + "\n" + result.stderr[-1000:])
        checks.append({"command": command, "elapsed_seconds": perf_counter() - started,
                       "exit_code": 0, "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest()})

    frontend = {"status":"not_run_by_collector"}
    if args.frontend:
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node.js is required for frontend verification")
        frontend = {"status":"passed","commands":[]}
        for entry in (("node_modules/typescript/bin/tsc","--noEmit"),("node_modules/next/dist/bin/next","build")):
            result = subprocess.run([node,*entry],cwd=ROOT / "frontend",env=environment,
                                    capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180)
            if result.returncode:
                raise RuntimeError("Frontend verification failed: " + entry[0] + "\n" + result.stderr[-1000:])
            frontend["commands"].append({"command":"node " + " ".join(entry),"exit_code":0,
                "stdout_sha256":hashlib.sha256(result.stdout.encode()).hexdigest()})

    os.environ.update(environment)
    from app.db import connect
    from app.kb_sync import assert_complete
    with connect() as connection:
        channel = connection.execute("SELECT snapshot_id,activated_at FROM kb_channels WHERE namespace='runtime'").fetchone()
        if not channel:
            raise ValueError("No active runtime deployment")
        assert_complete(connection,"runtime",channel["snapshot_id"])
        snapshot = connection.execute("SELECT * FROM kb_snapshots WHERE namespace='runtime' AND snapshot_id=%s",
                                      (channel["snapshot_id"],)).fetchone()
        deployment = {
            "snapshot_id": channel["snapshot_id"],
            "activated_at": channel["activated_at"].isoformat(),
            "registry_version": snapshot["registry_version"],
            "chunk_count": snapshot["chunk_count"],
            "concept_count": connection.execute("SELECT count(*) AS n FROM kb_concepts WHERE namespace='runtime' AND registry_version=%s",
                                                (snapshot["registry_version"],)).fetchone()["n"],
            "skill_count": connection.execute("SELECT count(*) AS n FROM kb_skills WHERE namespace='runtime' AND registry_version=%s",
                                              (snapshot["registry_version"],)).fetchone()["n"],
            "example_count": connection.execute("""SELECT count(*) AS n FROM kb_snapshot_members m
                JOIN kb_chunks c USING(namespace,content_id,content_version)
                WHERE m.namespace='runtime' AND m.snapshot_id=%s AND c.kind='example'""",
                (channel["snapshot_id"],)).fetchone()["n"],
            "member_count": connection.execute("SELECT count(*) AS n FROM kb_snapshot_members WHERE namespace='runtime' AND snapshot_id=%s",
                                               (channel["snapshot_id"],)).fetchone()["n"],
            "latest_syncs": connection.execute("""SELECT status,summary FROM kb_sync_runs
                WHERE namespace='runtime' AND snapshot_id=%s ORDER BY started_at DESC LIMIT 2""",
                (channel["snapshot_id"],)).fetchall(),
        }
    if (deployment["snapshot_id"] != acceptance["runtime_active_snapshot"]
            or deployment["registry_version"] != "0.4.0-member2-review"
            or (deployment["chunk_count"],deployment["member_count"]) != (91,91)
            or (deployment["concept_count"],deployment["skill_count"]) != (40,40)
            or deployment["example_count"] != 39):
        raise ValueError("Active runtime deployment does not match acceptance")
    latest = deployment["latest_syncs"][0]
    if (latest["status"] != "published" or latest["summary"]["inserted_chunks"] != 0
            or latest["summary"]["computed_embeddings"] != 0
            or latest["summary"]["cached_embeddings"] != 91):
        raise ValueError("Latest runtime sync is not idempotent")

    OUT.mkdir(parents=True, exist_ok=True)
    acceptance_out = OUT / "acceptance-2026-11-26.json"
    tests_out = OUT / "tests-2026-11-26.xml"
    acceptance_out.write_bytes(acceptance_path.read_bytes())
    shutil.copyfile(tests_path, tests_out)
    retrieval = {
        "checked_at": evidence["checked_at"],
        "benchmark": "research/retrieval/dev/member2-13.v1",
        "concept_count": 13, "document_count": 91, "query_count": 104,
        "judgment_count": 169, "fallback_query_count": 13,
        "queries_sha256": acceptance["queries_sha256"], "qrels_sha256": acceptance["qrels_sha256"],
        "summary": acceptance["dev_summary"], "summary_by_concept": acceptance["dev_summary_by_concept"],
        "label_limit": "deterministic development judgments; not independent human gold or final RQ3",
    }
    retrieval_out = OUT / "retrieval-evaluation-2026-11-26.json"
    write(retrieval_out, retrieval)
    checks_out = OUT / "checks-2026-11-26.json"
    write(checks_out, checks)
    trace_out = OUT / "retrieval-traces-2026-11-26.json"
    write(trace_out,{"usage":"retrieval_only_not_delivery","traces":acceptance["retrieval_trace_data"]})
    source_paths = [
        "backend/app/kb_contracts.py","backend/app/kb_projection.py","backend/app/kb_cli.py",
        "scripts/kb/build_member2_stage3_assets.py","scripts/checks/check_stage3_kb.py",
        "scripts/checks/check_member2_ai_review.py","scripts/checks/collect_stage3_completion.py",
        "tests/test_kb_db.py","tests/test_stage3_completion.py",".github/workflows/repository-checks.yml",
        "content/kb/member2-v2/manifest.json","research/retrieval/dev/member2-13.v1/manifest.json",
    ]
    import yaml
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load((ROOT / ".github/workflows/repository-checks.yml").read_text(encoding="utf-8"))
    if (not compose["services"]["db"]["image"].startswith("pgvector/pgvector:")
            or not workflow["jobs"]["checks"]["services"]["postgres"]["image"].startswith("pgvector/pgvector:")):
        raise ValueError("Compose/CI must use pgvector PostgreSQL")
    completion = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "stage": "Member 2 Chặng 3", "status": "local_complete_external_acceptance_pending",
        "implemented_scope":"13 approved concepts with 39 verbatim reviewed worked examples",
        "runtime_deployment": deployment, "pytest": test_summary,
        "checkers_passed": len(checks), "real_db_and_pgvector": True,
        "real_local_embedding": True, "model_api_calls": 0,
        "acceptance_schema_isolated_and_removed": True,
        "frontend":frontend,"compose_and_ci_yaml":"passed",
        "docker_execution": "not_run_no_docker" if not shutil.which("docker") else "not_run_by_collector",
        "remote_ci": "not_run_workspace_has_no_git_or_connected_repository",
        "independent_member1_member3_signoff":"pending_external_review",
        "source_file_sha256":{name:sha(ROOT / name) for name in source_paths},
        "agent_retrieval_integration": False,
        "remaining_scope": "Agent/generator/UI retrieval use belongs to Chặng 4; final held-out RQ3 belongs to Chặng 6.",
        "evidence_sha256": {path.name: sha(path) for path in (acceptance_out, tests_out, retrieval_out, checks_out,trace_out)},
    }
    completion_out = OUT / "completion-2026-11-26.json"
    write(completion_out, completion)
    print(json.dumps({"status":"passed", "tests":test_summary["tests"], "checks":len(checks),
                      "snapshot_id":deployment["snapshot_id"], "chunks":deployment["chunk_count"],
                      "evidence":str(completion_out.relative_to(ROOT))}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
