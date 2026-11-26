"""Run the maintained release plus main's tests; explicitly list unavailable archives.

Use pytest tests directly for the historical full suite after restoring the
original, hash-pinned archive. This selection never claims those tests passed.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_TESTS = [
    'tests/test_content_authoring.py',
    'tests/test_kb_db.py',
    'tests/test_kb_unit.py',
    'tests/test_member2_foundation.py',
    'tests/test_member2_stage2_pilot.py',
    'tests/test_oatutor_pilot.py',
    'tests/test_stage2_completion.py',
]
ARCHIVE_CASES = [
    'tests/test_retrieval_benchmark.py::test_real_sync_idempotency_hash_lock_and_metadata_filters',
    'tests/test_retrieval_benchmark.py::test_failed_sync_rolls_back_snapshot_and_chunks',
    'tests/test_retrieval_benchmark.py::test_unknown_model_and_concept_skill_pair_return_no_content',
]
REQUIRED_ARCHIVES = ['content/authoring/batches/a02-e02-oatutor.v2',
                     'content/authoring/configs/a02.v1.json']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junitxml', default='artifacts/current-release-tests.xml')
    parser.add_argument('--maxfail', type=int, default=0)
    parser.add_argument('--collect-only', action='store_true')
    args = parser.parse_args()
    missing = [name for name in REQUIRED_ARCHIVES if not (ROOT / name).exists()]
    exclusions = ARCHIVE_TESTS if missing else []
    cases = ARCHIVE_CASES if missing else []
    print(json.dumps({'scope': 'current_release_and_main', 'historical_full_suite': not missing,
        'unavailable_archives': missing, 'excluded_modules': exclusions, 'excluded_cases': cases}), flush=True)
    command = [sys.executable, '-m', 'pytest', 'tests', '-q', '--disable-warnings',
               '-o', 'cache_dir=artifacts/release-pytest-cache', '--junitxml=' + args.junitxml]
    command += ['--ignore=' + name for name in exclusions]
    command += ['--deselect=' + name for name in cases]
    if args.maxfail: command += ['--maxfail=' + str(args.maxfail)]
    if args.collect_only: command += ['--collect-only']
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
