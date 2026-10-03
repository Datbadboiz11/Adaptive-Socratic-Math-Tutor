"""One explicitly enabled paid request in an isolated schema; no secrets in evidence."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
parser=argparse.ArgumentParser()
parser.add_argument('--live-openai',action='store_true')
args=parser.parse_args()
if not args.live_openai: raise SystemExit('Pass --live-openai to authorize one bounded live model request')
v={}
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k,value=line.split('=',1); v[k.strip()]=value.strip().strip('"').strip("'")
os.environ.update(PGHOST='127.0.0.1',PGPORT=v.get('POSTGRES_PORT','5433'),PGDATABASE=v.get('POSTGRES_DB','mo_tutor_dev'),
    PGUSER=v.get('POSTGRES_USER','mo_dev'),PGPASSWORD=v['POSTGRES_PASSWORD'],DEMO_MODE='true',TUTOR_ENABLED='true',
    OPENAI_API_KEY=v.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY',''),OPENAI_MODEL=v.get('OPENAI_MODEL') or 'gpt-4o-mini',
    LLM_ENABLED='true',VALIDATOR_TIMEOUT_SECONDS='3')
os.environ.pop('DATABASE_URL',None)
from psycopg import sql
from fastapi.testclient import TestClient
from app.db import connect
from app.manage import migrate,seed
from app.main import app
name='test_live_'+uuid4().hex
with connect() as c: c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
os.environ['PGOPTIONS']=f'-c search_path={name}'
try:
    with connect() as c: migrate(c); seed(c)
    with TestClient(app) as c:
        token=c.post('/api/v1/demo/login',json={'demo_profile_id':'DEMO-STUDENT-01'}).json()['access_token']
        h={'Authorization':'Bearer '+token}
        s=c.post('/api/v1/sessions',headers=h,json={'request_id':str(uuid4()),'demo_profile_id':'DEMO-STUDENT-01','topic_id':'TOPIC-LINEAR-01'}).json()
        for _ in range(2):
            s=c.post(f"/api/v1/sessions/{s['session_id']}/next",headers=h,json={'request_id':str(uuid4()),'expected_state_version':s['state_version']}).json()
        body={'request_id':str(uuid4()),'expected_state_version':s['state_version'],'opportunity_id':s['current_opportunity_id'],
              'action':'submit','steps':['2x-3=10','2x=13','x=6.5']}
        url=f"/api/v1/sessions/{s['session_id']}/turns"
        response=c.post(url,headers=h,json=body)
        assert response.status_code==200,response.text
        result=response.json()
        assert c.post(url,headers=h,json=body).json()==result
        report={'checked_at':datetime.now(timezone.utc).isoformat(),'live_success':result['response_source']=='openai',
            'scope':'One live call plus cached replay, synthetic content only; test schema removed.',
            'input':body['steps'],'result':result}
        out=ROOT/'docs/phase3/evidence/live-openai.json'; out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'live_success':report['live_success'],'source':result['response_source'],
            'assessment':result['assessment']['assessment_status'],'reason':result['assessment']['reason_code'],
            'model':result['tutor'].get('model'),'fallback_reason':result['tutor'].get('fallback_reason'),
            'usage':result['tutor'].get('usage')},ensure_ascii=True))
        assert result['assessment']['first_error_step']==1
        assert 'x = 8' not in result['message'] and 'x=8' not in result['message']
        if not report['live_success']: raise SystemExit(2)
finally:
    os.environ.pop('PGOPTIONS',None)
    assert name.startswith('test_live_') and len(name)==42
    with connect() as c: c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
