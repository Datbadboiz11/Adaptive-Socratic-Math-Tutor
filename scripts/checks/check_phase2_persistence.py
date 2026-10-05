"""Create one demo session; optionally restart local Compose backend and stop DB briefly.

Only --exercise-recovery touches container availability; existing volumes are kept.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.error
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--exercise-recovery', action='store_true')
args = parser.parse_args()
token = None
def api(path, body=None, method=None):
    request = urllib.request.Request('http://127.0.0.1:8000' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)

def ready():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if api('/health/ready')[0] == 200: return
        except (OSError, TimeoutError): pass
        time.sleep(0.5)
    raise RuntimeError('Backend did not recover within 60 seconds')

checks = []
code, login = api('/api/v1/demo/login', {'demo_profile_id':'DEMO-STUDENT-01'})
assert code == 200
token = login['access_token']
code, s = api('/api/v1/sessions', {'request_id':str(uuid4()), 'demo_profile_id':'DEMO-STUDENT-01', 'topic_id':'TOPIC-LINEAR-01'})
assert code == 201
path = '/api/v1/sessions/' + s['session_id']
turn = {'request_id':str(uuid4()), 'expected_state_version':s['state_version'], 'opportunity_id':s['current_opportunity_id'], 'action':'submit', 'steps':['3x=15','x=5']}
code, result = api(path + '/turns', turn)
assert code == 200
s = result['session']
if args.exercise_recovery:
    subprocess.run(['docker','compose','restart','backend'], cwd=ROOT, check=True)
    ready()
    assert api(path)[1] == s
    assert api(path + '/turns', turn)[1] == result
    checks.append('backend restart retains session, token and cached mutation response')
    mutation = {'request_id':str(uuid4()), 'expected_state_version':s['state_version'], 'draft':'Nháp phục hồi sau khi DB tạm dừng'}
    try:
        subprocess.run(['docker','compose','stop','db'], cwd=ROOT, check=True)
        assert api('/health/ready')[0] == 503
        code, error = api(path + '/draft', mutation, 'PUT')
        assert code == 503 and error['retryable'] is True
        assert 'password' not in json.dumps(error).lower()
    finally:
        subprocess.run(['docker','compose','up','-d','--wait','db'], cwd=ROOT, check=True)
        ready()
    code, s = api(path + '/draft', mutation, 'PUT')
    assert code == 200 and s['draft'] == mutation['draft']
    assert api(path + '/draft', mutation, 'PUT')[1] == s
    checks.append('DB outage returns 503; same request saves once after recovery')
else:
    assert api(path + '/turns', turn)[1] == result
    checks.append('same request replay matches stored response')
assert len(s['turns']) == 1 and s['eligible_observations'] == 0
code, report = api(path + '/finish', {'request_id':str(uuid4()), 'expected_state_version':s['state_version']})
assert code == 200 and report['submitted_turns'] == 1 and report['valid_observations'] == 0
assert api(path + '/report')[1] == report
checks.append('report reads the same committed turn without observations')
out = ROOT / 'docs/implementation/mvp/phase2/evidence/persistence-check.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),
    'recovery_exercised':args.exercise_recovery, 'session_id':s['session_id'], 'checks':checks,
    'report': report}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'PASS: {len(checks)} persistence checks')
