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
from pathlib import Path
import sys
from typing import Callable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decide import RulePolicyProposer, run_decision  # noqa: E402
from app.agent.decision import ExperimentConfiguration  # noqa: E402
from app.llm.fakes import FakeLLMClient  # noqa: E402
from app.agent.llm_proposer import LLMProposer, decision_config, proposal_to_output  # noqa: E402
from app.agent.rule_policy import rule_policy  # noqa: E402
from research.agent.scenarios import Scenario, load_scenarios  # noqa: E402
from research.llm_support import (  # noqa: E402
    DEFAULT_MAX_CALLS, format_ms, format_usage, real_client, timing_stats, usage_summary,
)

FULL, RULE = ExperimentConfiguration.FULL, ExperimentConfiguration.RULE_POLICY


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

def summarize(rows: list[dict]) -> dict[str, dict]:
    """Thống kê theo proposer.

    ``decision_ms`` là cả chuỗi proposer → gate → fallback, có cho mọi proposer. Các số về lần gọi
    model (``api_ms``, token, chi phí) theo ``llm_support.usage_summary``."""
    out = {}
    for label in dict.fromkeys(r["proposer"] for r in rows):
        group = [r for r in rows if r["proposer"] == label]
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
            "decision_ms": timing_stats([r["decision_ms"] for r in group]),
            **usage_summary([r["usage"] for r in group if r["usage"]]),
        }
    return out


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
        print(f"    decision_ms {format_ms(s['decision_ms'])}")
        for line in format_usage(s):
            print(line)


# --------------------------------------------------------------------------- CLI

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
        client = real_client(len(scenarios) * args.repeat, f"{len(scenarios)} tình huống × {args.repeat}",
                             max_calls=args.max_calls, confirmed=args.yes)
        if client is None:
            return 2
        agent = LLMProposer(client)

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
