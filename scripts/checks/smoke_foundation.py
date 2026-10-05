"""Read-only smoke checks against the local foundation; never calls OpenAI."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--backend", default="http://127.0.0.1:8000")
parser.add_argument("--frontend", default="http://127.0.0.1:3000")
parser.add_argument("--database-down", action="store_true")
args = parser.parse_args()


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


checks = []
code, raw = get(args.backend + "/health/live")
body = json.loads(raw)
assert code == 200 and isinstance(body["tutoring_enabled"], bool)
checks.append({"check": "liveness", "http_status": code, "response": body})
code, raw = get(args.backend + "/health/ready")
body = json.loads(raw)
assert code == (503 if args.database_down else 200)
assert body["database"] == ("unavailable" if args.database_down else "connected")
checks.append({"check": "database_readiness", "http_status": code, "response": body})
code, html = get(args.frontend)
expected = "Chưa kết nối" if args.database_down else "Đã kết nối cơ sở dữ liệu"
assert code == 200 and expected in html
checks.append({"check": "frontend_displays_live_readiness", "http_status": code, "expected_text_found": True})
code, raw = get(args.backend + "/openapi.json")
paths = json.loads(raw)["paths"]
assert code == 200 and {"/health/live", "/health/ready", "/api/v1/sessions"}.issubset(paths)
checks.append({"check": "health_and_session_endpoints_exposed", "paths": sorted(paths)})

report = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "mode": "database_down" if args.database_down else "ready",
    "checks": checks,
    "scope": "Foundation connectivity only; no tutoring, BKT or OpenAI request.",
}
target = ROOT / "docs/implementation/mvp/phase3/evidence" / ("smoke-db-down.json" if args.database_down else "smoke-ready.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"PASS: {len(checks)} foundation smoke checks ({report['mode']})")
