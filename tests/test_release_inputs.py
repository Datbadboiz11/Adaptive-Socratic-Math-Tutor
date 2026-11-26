"""Regression: a PR must retain deployment entry points and required source data."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_current_checkout_contains_shared_deployment_and_release_inputs():
    result = subprocess.run([sys.executable, 'scripts/checks/check_release_inputs.py'],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '"registry_concepts": 40' in result.stdout
    assert '"neo4j"' in result.stdout


def test_incomplete_checkout_fails_before_dependency_install(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/checks/check_release_inputs.py'),
                             '--root', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode != 0
    for name in ('README.md', 'compose.yaml', 'registry.v2.json', 'pilot.v2.json'):
        assert name in result.stderr
    assert 'Traceback' not in result.stderr
