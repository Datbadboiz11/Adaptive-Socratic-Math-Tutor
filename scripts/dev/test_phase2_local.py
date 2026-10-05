"""Run isolated DB tests using this project's local Compose connection settings."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
env = dict(os.environ)
values = {}
for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
env.update(PGHOST='127.0.0.1', PGPORT=values.get('POSTGRES_PORT', '5433'),
           PGDATABASE=values.get('POSTGRES_DB', 'mo_tutor_dev'), PGUSER=values.get('POSTGRES_USER', 'mo_dev'),
           PGPASSWORD=values['POSTGRES_PASSWORD'], RUN_DB_TESTS='1', DEMO_MODE='true')
env.pop('DATABASE_URL', None)
(ROOT / 'docs/implementation/mvp/phase2/evidence').mkdir(parents=True, exist_ok=True)
raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', 'tests/test_phase1.py', 'tests/test_phase2.py', '-q',
                                 '--junitxml=docs/implementation/mvp/phase2/evidence/tests.xml'], cwd=ROOT, env=env))
