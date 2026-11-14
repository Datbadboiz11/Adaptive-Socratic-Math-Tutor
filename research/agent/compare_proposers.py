"""So sánh Agent LLM với Rule-policy trên bộ tình huống dev (RQ5, đo latency/cost).

Mỗi tình huống chạy qua đúng chuỗi của hệ thống: proposer → policy gate → fallback
(``decide.resolve_decision``). Rule-policy luôn được chạy làm mốc, không tốn API.

    python research/agent/compare_proposers.py                      # chỉ Rule-policy
    python research/agent/compare_proposers.py --agent fake         # đường Agent với LLM giả, không gọi API
    python research/agent/compare_proposers.py --agent openai --yes # GỌI API THẬT, tốn phí

``--agent openai`` cần ``LLM_ENABLED=true`` và ``OPENAI_API_KEY`` trong ``.env`` (hoặc biến môi
trường); script in số lần gọi dự kiến rồi mới chạy, và dừng nếu thiếu ``--yes``. Kết quả thô ghi
bằng ``--out`` vào ``data/`` (đã ignore). Đây là bộ dev để phát triển prompt, không phải test
chính thức (plan §11.5, §19.3): không dùng số liệu ở đây làm kết quả RQ5.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Callable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decide import RulePolicyProposer, run_decision  # noqa: E402
from app.agent.decision import ExperimentConfiguration  # noqa: E402
from app.agent.llm import LLMDisabled, LLMSettings, OpenAIResponsesClient  # noqa: E402
from app.agent.llm_proposer import LLMProposer, decision_config, proposal_to_output  # noqa: E402
from app.agent.rule_policy import rule_policy  # noqa: E402
from app.agent.fakes import FakeLLMClient  # noqa: E402
from research.agent.scenarios import Scenario, load_scenarios  # noqa: E402

FULL, RULE = ExperimentConfiguration.FULL, ExperimentConfiguration.RULE_POLICY
DEFAULT_MAX_CALLS = 50


# --------------------------------------------------------------------------- chạy

def run_one(sc: Scenario, label: str, proposer, configuration: ExperimentConfiguration, attempt: int) -> dict:
    record = run_decision(sc.state, sc.context, proposer, decision_config(configuration, proposer),
                          decision_id=uuid4(), created_at=datetime.now(timezone.utc))
    proposed, final, usage = record.proposed, record.final, record.agent_usage
    return {
        "scenario": sc.id, "proposer": label, "attempt": attempt, "configuration": configuration.value,
        "proposed_action": proposed.action.value if proposed else None,
        "proposed_intent": proposed.intent.value if proposed else None,
        "gate": record.gate.status if record.gate else None,
        "violated_rules": record.gate.violated_rules if record.gate else [],
        "final_source": record.final_source.value, "fallback_reason": record.fallback_reason,
        "final_action": final.action.value, "final_intent": final.intent.value,
        "final_acceptable": final.action.value in sc.acceptable_actions,
        "proposed_forbidden": bool(proposed) and proposed.action.value in sc.forbidden_actions,
        "same_as_rule": bool(proposed) and (proposed.action.value, proposed.intent.value)
                        == (sc.expected_rule_action, sc.expected_rule_intent),
        "reason": proposed.reason if proposed else None,
        "decision_ms": record.decision_latency_ms,
        "usage": usage.model_dump(mode="json") if usage else None,
        "decision": record.model_dump(mode="json"),
    }


def run_comparison(scenarios: list[Scenario], agent: LLMProposer | None, repeat: int = 1,
                   before_agent_call=None) -> list[dict]:
    """``before_agent_call(sc)`` cho phép chạy thử nạp đầu ra cho LLM giả trước mỗi lần gọi."""
    rows = [run_one(sc, "rule_policy", RulePolicyProposer(), RULE, 1) for sc in scenarios]
    if agent is not None:
        for attempt in range(1, repeat + 1):
            for sc in scenarios:
                if before_agent_call is not None:
                    before_agent_call(sc)
                rows.append(run_one(sc, "agent", agent, FULL, attempt))
    return rows


# --------------------------------------------------------------------------- tổng hợp

def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def _stats(values: list[float]) -> dict:
    return {"median": statistics.median(values) if values else None, "p95": _percentile(values, 0.95)}


def summarize(rows: list[dict]) -> dict[str, dict]:
    """Thống kê theo proposer.

    - ``decision_ms``: cả chuỗi proposer → gate → fallback, có cho mọi proposer.
    - ``api_ms``: riêng lần gọi model, chỉ tính trên các lần có gọi.
    - Token chỉ tính trên các lần provider trả ``usage`` (``usage_known``); lần thiếu (timeout,
      lỗi mạng) được đếm riêng ở ``usage_missing``, không tính thành 0.
    - ``cost_usd_known`` là tổng của ``cost_known_calls`` / ``llm_calls`` lần gọi; khác nhau nghĩa
      là chi phí thật có thể cao hơn."""
    out = {}
    for label in dict.fromkeys(r["proposer"] for r in rows):
        group = [r for r in rows if r["proposer"] == label]
        calls = [r["usage"] for r in group if r["usage"]]
        known = [u for u in calls if u["input_tokens"] is not None]
        costs = [u["cost_usd"] for u in calls if u["cost_usd"] is not None]
        reasons = {}
        for r in group:
            if r["fallback_reason"]:
                reasons[r["fallback_reason"]] = reasons.get(r["fallback_reason"], 0) + 1
        out[label] = {
            "runs": len(group),
            "gate_accepted": sum(r["gate"] == "accepted" for r in group),
            "fallbacks": reasons,
            "final_acceptable": sum(r["final_acceptable"] for r in group),
            "proposed_forbidden": sum(r["proposed_forbidden"] for r in group),
            "same_as_rule": sum(r["same_as_rule"] for r in group),
            "decision_ms": _stats([r["decision_ms"] for r in group]),
            "llm_calls": len(calls),
            "api_ms": _stats([u["latency_ms"] for u in calls]),
            "usage_known": len(known),
            "usage_missing": len(calls) - len(known),
            "input_tokens_mean": statistics.mean(u["input_tokens"] for u in known) if known else None,
            "cached_input_tokens_total": sum(u["cached_input_tokens"] for u in known),
            "output_tokens_mean": statistics.mean(u["output_tokens"] for u in known) if known else None,
            "cost_known_calls": len(costs),
            "cost_usd_known": round(sum(costs), 6) if costs else None,
        }
    return out


def _ms(stats: dict) -> str:
    if stats["median"] is None:
        return "-"
    return f"median={stats['median']:.1f} p95={stats['p95']:.1f}"


def print_report(rows: list[dict], summary: dict[str, dict]) -> None:
    print(f"{'scenario':9} {'proposer':12} {'proposed':38} {'gate':9} {'final':38} ok  rules")
    for r in rows:
        proposed = (f"{r['proposed_action']}/{r['proposed_intent']}" if r["proposed_action"]
                    else f"(none: {r['fallback_reason']})")
        print(f"{r['scenario']:9} {r['proposer']:12} {proposed:38} {r['gate'] or '-':9} "
              f"{r['final_action'] + '/' + r['final_intent']:38} {'yes' if r['final_acceptable'] else 'NO ':3} "
              f"{','.join(r['violated_rules'])}")
    print()
    for label, s in summary.items():
        print(f"[{label}] runs={s['runs']} gate_accepted={s['gate_accepted']} fallbacks={s['fallbacks']} "
              f"final_acceptable={s['final_acceptable']} proposed_forbidden={s['proposed_forbidden']} "
              f"same_as_rule={s['same_as_rule']}")
        print(f"    decision_ms {_ms(s['decision_ms'])}")
        if s["llm_calls"]:
            tokens = (f"input_tokens_mean={s['input_tokens_mean']:.0f} cached_total={s['cached_input_tokens_total']} "
                      f"output_tokens_mean={s['output_tokens_mean']:.0f}") if s["usage_known"] else "tokens=-"
            print(f"    llm_calls={s['llm_calls']} api_ms {_ms(s['api_ms'])} usage_known={s['usage_known']} "
                  f"usage_missing={s['usage_missing']} {tokens}")
            print(f"    cost_usd_known={s['cost_usd_known']} (from {s['cost_known_calls']}/{s['llm_calls']} calls)")


# --------------------------------------------------------------------------- CLI

def read_env(path: Path = ROOT / ".env") -> dict[str, str]:
    """Biến trong ``.env`` (nếu có), bị biến môi trường ghi đè. Không in giá trị nào."""
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return {**values, **os.environ}


def fake_agent() -> tuple[LLMProposer, Callable[[Scenario], None]]:
    """LLM giả trả đúng đề xuất của Rule-policy: kiểm tra đường Agent (prompt, schema, parse, gate,
    log) mà không tốn API. Kết quả của nó KHÔNG phản ánh chất lượng của model thật."""
    client = FakeLLMClient()
    return LLMProposer(client), lambda sc: client.push(proposal_to_output(rule_policy(sc.state, sc.context)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", choices=["none", "fake", "openai"], default="none")
    parser.add_argument("--scenarios", nargs="*", help="ID tình huống, mặc định chạy tất cả")
    parser.add_argument("--repeat", type=int, default=1, help="số lần chạy Agent trên mỗi tình huống")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                        help="trần số lần gọi model, dừng trước khi chạy nếu vượt")
    parser.add_argument("--yes", action="store_true", help="xác nhận gọi API thật (--agent openai)")
    parser.add_argument("--out", type=Path, help="ghi từng lượt chạy ra JSONL, ví dụ data/agent_runs/dev.jsonl")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")

    scenarios = load_scenarios(args.scenarios or None)
    agent, before = None, None
    if args.agent == "fake":
        agent, before = fake_agent()
    elif args.agent == "openai":
        calls = len(scenarios) * args.repeat
        try:
            settings = LLMSettings.from_env(read_env())
        except LLMDisabled as error:
            print(f"Không gọi API: {error}. Điền OPENAI_API_KEY và đặt LLM_ENABLED=true trong .env.",
                  file=sys.stderr)
            return 2
        print(f"Sẽ gọi {settings.model} {calls} lần ({len(scenarios)} tình huống × {args.repeat}), "
              f"timeout {settings.timeout_seconds}s mỗi lần.")
        if calls > args.max_calls:
            print(f"Vượt --max-calls={args.max_calls}; dừng.", file=sys.stderr)
            return 2
        if not args.yes:
            print("Thêm --yes để xác nhận gọi API thật.", file=sys.stderr)
            return 2
        agent = LLMProposer(OpenAIResponsesClient(settings))

    rows = run_comparison(scenarios, agent, args.repeat, before)
    summary = summarize(rows)
    print_report(rows, summary)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nĐã ghi {len(rows)} dòng vào {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
