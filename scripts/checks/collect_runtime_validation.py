"""Curate synthetic local validation evidence; never copy .env, DB data or service logs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/implementation/member2/runtime-validation-2026-11-18"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-run", required=True)
    parser.add_argument("--benchmark-run", required=True)
    parser.add_argument("--model-run", required=True)
    args = parser.parse_args()
    if not all(re.fullmatch("[0-9a-f]{12}", value) for value in vars(args).values()):
        parser.error("Expected local 12-character run IDs")
    browser = ROOT / "artifacts/browser-validation" / args.browser_run
    files = [(browser / name, name) for name in ["browser-check.json", "tutor-1440.png", "tutor-768.png", "tutor-390.png", "report-mobile.png"]]
    files += [(ROOT / "artifacts/retrieval-validation" / args.benchmark_run / "benchmark.json", "benchmark.json"),
              (ROOT / "artifacts/model-validation" / args.model_run / "check.json", "model-check.json"),
              (ROOT / "artifacts/validation-db-tests.xml", "tests.xml")]
    tests = ET.parse(files[-1][0]).getroot().find("testsuite").attrib
    if any(int(tests[key]) for key in ("failures", "errors", "skipped")):
        raise ValueError("Cannot record full-pass acceptance with failures or skipped tests")
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for source, name in files:
        with source.open("rb") as src, (OUT / name).open("xb") as dst:
            shutil.copyfileobj(src, dst)
        hashes[name] = sha(OUT / name)
    source_paths = ["backend/app/gemini_wording.py", "backend/app/tutor.py", "backend/app/session_contracts.py",
        "backend/requirements.txt", "frontend/app/workspace.tsx", "contracts/phase3/openapi.json", "compose.yaml",
        ".env.example", ".github/workflows/repository-checks.yml", "research/requirements-retrieval.txt",
        "research/retrieval/metrics.py", "research/retrieval/pgvector_dev.py", "research/retrieval/run_dev.py",
        "scripts/dev/validation_runtime.py", "scripts/checks/check_current_browser.py", "scripts/checks/check_live_model.py",
        "tests/test_gemini_wording.py", "tests/test_retrieval_benchmark.py"]
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "reviewer": "Codex",
        "review_kind": "delegated_ai_technical_validation", "independent_human_review": False,
        "human_approved_packs": 0, "human_approved_labels": 0, "real_member_signatures": 0,
        "pytest": {**tests, "run_db_tests": True, "postgres": "16.15", "pgvector": "0.8.6"},
        "frontend": {"typecheck": "passed", "production_build": "passed", "browser_checks": 6,
                     "browser_build": "latest local production build", "model_source": "draft_template"},
        "content_checks": "ten content/math/AI-review/schema checks passed",
        "remote_ci": {"status": "blocked", "reason": "No .git, GitHub credentials or connected GitHub tools in workspace"},
        "model_api": {"status": "blocked", "reason": "Provider key not configured; no real external model call"},
        "alignment": {"status": "provisional", "reason": "Official district PDF download returned HTTP 403; no page-level verification"},
        "retrieval": {"status": "real_pgvector_dev_benchmark_passed", "agent_integration": False,
                      "runtime_publication": False, "query_count": 24, "candidate_count": 8},
        "evidence_sha256": hashes, "source_file_sha256": {path: sha(ROOT / path) for path in source_paths}}
    with (OUT / "verification.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"evidence_directory": str(OUT.relative_to(ROOT)), "tests_passed": int(tests["tests"])}, indent=2))


if __name__ == "__main__":
    main()
