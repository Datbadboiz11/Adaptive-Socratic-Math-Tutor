"""All regression tests using Compose DB in isolated test schemas; no paid calls."""
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
values={}
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k,v=line.split('=',1); values[k.strip()]=v.strip().strip('"').strip("'")
env={**os.environ,'PYTHONUTF8':'1','PGHOST':'127.0.0.1','PGPORT':values.get('POSTGRES_PORT','5433'),
    'PGDATABASE':values.get('POSTGRES_DB','mo_tutor_dev'),'PGUSER':values.get('POSTGRES_USER','mo_dev'),
    'PGPASSWORD':values['POSTGRES_PASSWORD'],'RUN_DB_TESTS':'1','LLM_ENABLED':'false'}
env.pop('DATABASE_URL',None)
(ROOT/'docs/phase3/evidence').mkdir(parents=True,exist_ok=True)
raise SystemExit(subprocess.call([sys.executable,'-X','utf8','-m','pytest','tests','-q',
    '--junitxml=docs/phase3/evidence/tests.xml'],cwd=ROOT,env=env))
