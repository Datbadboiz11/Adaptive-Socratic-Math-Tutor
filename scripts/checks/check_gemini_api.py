"""One real, bounded Gemini request with allowlisted HTTP diagnostics; never prints keys."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/dev"))


def safe_error(response):
    result = {"http_status": response.status_code}
    if not response.is_error:
        return result
    try:
        error = response.json().get("error", {})
    except Exception:
        return result
    allowed_statuses = {"INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND",
                        "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION", "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED"}
    if error.get("status") in allowed_statuses:
        result["provider_error_status"] = error["status"]
    details = [d for d in error.get("details", []) if isinstance(d, dict)]
    known_reasons = {"API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED",
                     "API_KEY_IP_ADDRESS_BLOCKED", "SERVICE_DISABLED", "BILLING_DISABLED", "CONSUMER_INVALID",
                     "RATE_LIMIT_EXCEEDED", "ACCESS_TOKEN_EXPIRED"}
    result["provider_error_reasons"] = sorted({d["reason"] for d in details
        if isinstance(d.get("reason"), str) and d["reason"] in known_reasons})
    message = str(error.get("message", "")).lower()
    # Classifications are fixed strings. Never return the upstream error message or request.
    categories = {
        "invalid_api_key": ["api key not valid", "invalid api key"],
        "leaked_or_blocked_key": ["reported as leaked", "blocked api key"],
        "quota_or_rate_limit": ["quota", "rate limit", "resource exhausted"],
        "billing_requirement": ["billing"],
        "model_unavailable": ["not found", "not available", "not supported for generatecontent", "not have access"],
        "request_schema": ["responsejsonschema", "response_json_schema", "additionalproperties", "unknown name"],
        "location_restriction": ["user location is not supported", "not available in your country"],
    }
    result["error_categories"] = [label for label, terms in categories.items() if any(term in message for term in terms)]
    violations = [v for d in details for v in d.get("violations", []) if isinstance(v, dict)]
    result["quota_limit_zero_reported"] = any(str(v.get("quotaValue", "")) == "0" for v in violations)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Test this model without modifying .env")
    parser.add_argument("--call", action="store_true", help="Make one real generation request")
    args = parser.parse_args()
    from validation_runtime import local_environment
    os.environ.update(local_environment())
    key = os.getenv("GEMINI_API_KEY", "")
    model = args.model or os.getenv("GEMINI_MODEL", "")
    if not re.fullmatch(r"gemini-[A-Za-z0-9._-]{1,100}", model):
        parser.error("Configure a valid Gemini model name")
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "provider": "gemini",
              "key_present": bool(key), "requested_model": model, "generation_requests": 0,
              "max_output_tokens": 320, "synthetic_input": True, "status": "not_called"}
    if args.call and key:
        from app import gemini_wording
        original_client = gemini_wording.httpx.Client
        class DiagnosticClient(original_client):
            def post(self, *a, **kw):
                result["generation_requests"] += 1
                response = super().post(*a, **kw)
                result.update(safe_error(response))
                return response
        message = "Em hãy xem lại phép toán đã thực hiện ở cả hai vế nhé."
        state = {"problem": {"equation": "3*x+5=20"}, "steps": ["3*x=16"],
                 "validation": {"assessment": {"assessment_status": "verified_incorrect"}},
                 "policy": {"message": message, "candidates": [message, "Cùng tiếp tục nhé. " + message], "action": "hint"}}
        try:
            gemini_wording.httpx.Client = DiagnosticClient
            response = gemini_wording.select_wording(state, key, model)
        finally:
            gemini_wording.httpx.Client = original_client
        result.update(status="passed" if response.get("response_source") == "gemini" else "failed",
                      reason=response.get("fallback_reason"), response_source=response.get("response_source"),
                      model=response.get("model"), usage=response.get("usage"))
    elif not key:
        result.update(status="blocked", reason="missing_key")
    output = ROOT / "artifacts/model-validation" / uuid4().hex[:12] / "gemini-check.json"
    output.parent.mkdir(parents=True, exist_ok=False)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({**result, "evidence": str(output.relative_to(ROOT))}, ensure_ascii=True, indent=2))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
