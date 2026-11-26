"""One synthetic bounded model call. Keys stay in .env/environment; never write response bodies."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/dev"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-local", action="store_true")
    parser.add_argument("--provider", choices=["gemini", "openai"])
    parser.add_argument("--call", action="store_true", help="Make at most one real external API request")
    args = parser.parse_args()
    if args.workspace_local:
        from validation_runtime import local_environment
        os.environ.update(local_environment())
    provider = args.provider or os.getenv("LLM_PROVIDER", "openai")
    prefix = {"gemini": "GEMINI", "openai": "OPENAI"}.get(provider)
    configured = bool(prefix and os.getenv(prefix + "_API_KEY") and os.getenv(prefix + "_MODEL"))
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "provider": provider,
              "configured": configured, "max_requests": 1, "max_output_tokens": 320,
              "synthetic_input": True, "status": "not_called", "reason": "explicit_call_flag_required"}
    if not configured:
        result.update(status="blocked", reason="missing_provider_key_or_model")
    elif args.call:
        from app.tutor import model_wording
        os.environ.update(LLM_ENABLED="true", LLM_PROVIDER=provider)
        message = "Em hãy xem lại phép toán đã thực hiện ở cả hai vế nhé."
        response = model_wording({"problem": {"equation": "3*x+5=20"}, "steps": ["3*x=16"],
            "validation": {"assessment": {"assessment_status": "verified_incorrect"}},
            "policy": {"message": message, "candidates": [message, "Cùng tiếp tục nhé. " + message], "action": "hint"},
            "llm_allowed": True})
        result.update(status="passed" if response.get("response_source") == provider else "failed",
                      reason=response.get("fallback_reason"), response_source=response.get("response_source"),
                      model=response.get("model"), usage=response.get("usage"))
    output = ROOT / "artifacts/model-validation" / uuid4().hex[:12] / "check.json"
    output.parent.mkdir(parents=True, exist_ok=False)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({**result, "evidence": str(output.relative_to(ROOT))}, ensure_ascii=True, indent=2))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
