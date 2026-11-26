"""Đo bước sinh phản hồi trên bộ ca dev: verifier bắt đúng lỗi, và câu của generator qua được kiểm tra.

    python research/generation/evaluate_generation.py                      # chỉ verifier, không gọi API
    python research/generation/evaluate_generation.py --llm fake           # LLM giả trả câu oracle, không gọi API
    python research/generation/evaluate_generation.py --llm openai --yes   # GỌI API THẬT, tốn phí

Hai phần:
- Verifier (mọi chế độ): chạy ``ResponseVerifier`` trên câu oracle và các câu lỗi đã gán nhãn của
  từng ca, đếm đúng/sai theo từng loại lỗi.
- Generator (``--llm fake|openai``): mỗi ca chạy qua đúng chuỗi của hệ thống (``Responder``: LLM →
  kiểm tra → sinh lại tối đa 1 lần → template). Quyết định là của Rule-policy trên tình huống đó.

Verifier cho qua không có nghĩa câu đúng toán hay đúng sư phạm (PRD FR12-AC5): câu ghi bằng ``--out``
(vào ``data/``, đã ignore) là để người chấm độc lập theo rubric (plan §19.2). Đây là bộ dev tự soạn,
không phải test chính thức (plan §11.5, §19.3).
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decision import MAX_REGENERATIONS  # noqa: E402
from app.agent.kg_tool import skill_title  # noqa: E402
from app.agent.rule_policy import rule_policy  # noqa: E402
from app.agent.stubs import demo_answer_key, problem_prompt  # noqa: E402
from app.generation.contracts import Check, ResponseInput, response_input  # noqa: E402
from app.generation.llm_generator import PROMPT_VERSION, LLMResponseGenerator  # noqa: E402
from app.generation.responder import Responder  # noqa: E402
from app.generation.templates import TEMPLATE_VERSION, TemplateGenerator  # noqa: E402
from app.generation.verifier import VERIFIER_VERSION, ResponseVerifier  # noqa: E402
from app.llm.fakes import FakeLLMClient  # noqa: E402
from research.agent.scenarios import Scenario, load_scenarios  # noqa: E402
from research.llm_support import DEFAULT_MAX_CALLS, format_usage, real_client, usage_summary  # noqa: E402

CASES_PATH = ROOT / "contracts" / "generation" / "cases.dev.v1.json"
CALLS_PER_CASE = 1 + MAX_REGENERATIONS


@dataclass(frozen=True)
class Variant:
    id: str
    title: str
    message: str
    content_ids_used: tuple[str, ...]
    previous_messages: tuple[str, ...]
    expected: frozenset[str]


@dataclass(frozen=True)
class Case:
    id: str
    scenario: Scenario
    oracle: dict
    variants: tuple[Variant, ...]

    def input(self, previous_messages: tuple[str, ...] = ()) -> ResponseInput:
        sc = self.scenario
        return response_input(sc.state, rule_policy(sc.state, sc.context), sc.context, problem_prompt,
                              previous_messages, skill_title=skill_title)


@lru_cache(maxsize=1)
def _file() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def load_cases(ids: list[str] | None = None) -> list[Case]:
    data = _file()
    wanted = set(ids) if ids else None
    chosen = [c for c in data["cases"] if wanted is None or c["id"] in wanted]
    if wanted is not None and len(chosen) != len(wanted):
        raise KeyError(f"unknown case ids: {sorted(wanted - {c['id'] for c in chosen})}")
    scenarios = {sc.id: sc for sc in load_scenarios(sorted({c["scenario"] for c in chosen}))}
    return [Case(id=c["id"], scenario=scenarios[c["scenario"]], oracle=c["oracle"],
                 variants=tuple(Variant(id=v["id"], title=v["title"], message=v["message"],
                                        content_ids_used=tuple(v["content_ids_used"]),
                                        previous_messages=tuple(v.get("previous_messages", [])),
                                        expected=frozenset(v["expected"])) for v in c.get("variants", [])))
            for c in chosen]


def run_info(llm_mode: str, client=None) -> dict:
    """Phiên bản và cấu hình của lần chạy, ghi vào từng dòng kết quả để tái lập (NFR-04)."""
    return {"prompt_version": PROMPT_VERSION, "verifier_version": VERIFIER_VERSION,
            "template_version": TEMPLATE_VERSION, "llm": llm_mode, "model": getattr(client, "model", None),
            "cases_file": CASES_PATH.name, "cases_split": _file()["split"]}


# --------------------------------------------------------------------------- verifier

def check_verifier(cases: list[Case], verifier: ResponseVerifier) -> list[dict]:
    """Câu oracle phải qua (không lỗi nào); câu lỗi phải bị báo đúng tập lỗi đã gán nhãn."""
    rows = []
    for case in cases:
        items = [(case.id, "oracle", case.oracle["message"], tuple(case.oracle["content_ids_used"]), (), frozenset())]
        items += [(v.id, "variant", v.message, v.content_ids_used, v.previous_messages, v.expected)
                  for v in case.variants]
        for item_id, kind, message, used, previous, expected in items:
            found = frozenset(c.value for c in verifier.check_generated(case.input(previous), message, list(used)))
            rows.append({"id": item_id, "case": case.id, "kind": kind, "expected": sorted(expected),
                         "found": sorted(found), "exact": found == expected})
    return rows


def summarize_verifier(rows: list[dict]) -> dict:
    per_check = {}
    for check in Check:
        tp = sum(check in r["found"] and check in r["expected"] for r in rows)
        fp = sum(check in r["found"] and check not in r["expected"] for r in rows)
        fn = sum(check not in r["found"] and check in r["expected"] for r in rows)
        if tp or fp or fn:
            per_check[check.value] = {"tp": tp, "fp": fp, "fn": fn}
    oracle = [r for r in rows if r["kind"] == "oracle"]
    return {"items": len(rows), "exact": sum(r["exact"] for r in rows),
            "oracle_passed": sum(not r["found"] for r in oracle), "oracles": len(oracle), "per_check": per_check}


# --------------------------------------------------------------------------- generator

def run_case(case: Case, responder: Responder, run: dict | None = None) -> dict:
    inp = case.input()
    outcome = responder.run(inp)
    attempts = outcome.attempts
    first = attempts[0]
    return {
        "case": case.id, "scenario": case.scenario.id, "action": inp.decision.action.value,
        "intent": inp.decision.intent.value, "hint_level": inp.decision.hint_level,
        "final_source": outcome.final_source, "message": outcome.message,
        "first_accepted": first.source == "llm" and first.accepted,
        "first_violations": [v.value for v in first.violations] if first.source == "llm" else [],
        "regenerations_used": outcome.regenerations_used,
        "usages": [a.usage.model_dump(mode="json") for a in attempts if a.usage is not None],
        "attempts": [a.model_dump(mode="json") for a in attempts],
        "run": run,
    }


def evaluate(cases: list[Case], client, before_case=None, run: dict | None = None) -> list[dict]:
    """``before_case(case)`` cho phép nạp đầu ra cho LLM giả trước mỗi ca."""
    responder = Responder(TemplateGenerator(), ResponseVerifier(demo_answer_key), LLMResponseGenerator(client))
    rows = []
    for case in cases:
        if before_case is not None:
            before_case(case)
        rows.append(run_case(case, responder, run))
    return rows


def oracle_client() -> tuple[FakeLLMClient, Callable[[Case], None]]:
    """LLM giả trả đúng câu ``oracle`` của ca (cả khi được yêu cầu sinh lại): kiểm tra đường LLM
    (prompt, schema, verifier, log) mà không tốn API. Kết quả KHÔNG phản ánh chất lượng model thật."""
    client = FakeLLMClient()

    def before_case(case: Case) -> None:
        client.outputs.clear()
        for _ in range(CALLS_PER_CASE):
            client.push(case.oracle)

    return client, before_case


def summarize(rows: list[dict]) -> dict:
    sources = {}
    violations = {}
    for r in rows:
        sources[r["final_source"]] = sources.get(r["final_source"], 0) + 1
        for a in r["attempts"]:
            if a["source"] == "llm":
                for v in a["violations"]:
                    violations[v] = violations.get(v, 0) + 1
    return {
        "cases": len(rows), "final_sources": sources,
        "first_accepted": sum(r["first_accepted"] for r in rows),
        "regenerated": sum(r["regenerations_used"] > 0 for r in rows),
        "llm_violations": violations,
        **usage_summary([u for r in rows for u in r["usages"]]),
    }


# --------------------------------------------------------------------------- báo cáo

def print_verifier_report(rows: list[dict], s: dict) -> None:
    print(f"{'item':8} {'ok':3} {'expected':40} found")
    for r in rows:
        print(f"{r['id']:8} {'yes' if r['exact'] else 'NO ':3} {','.join(r['expected']) or '-':40} "
              f"{','.join(r['found']) or '-'}")
    print(f"\n[verifier] items={s['items']} exact={s['exact']} oracle_passed={s['oracle_passed']}/{s['oracles']}")
    for check, c in s["per_check"].items():
        print(f"    {check:20} tp={c['tp']} fp={c['fp']} fn={c['fn']}")


def print_generation_report(rows: list[dict], s: dict) -> None:
    print(f"\n{'case':6} {'intent':24} {'source':18} {'regen':5} first_violations")
    for r in rows:
        print(f"{r['case']:6} {r['intent']:24} {r['final_source']:18} {r['regenerations_used']:<5} "
              f"{','.join(r['first_violations']) or '-'}")
    print(f"\n[generator] cases={s['cases']} first_accepted={s['first_accepted']} regenerated={s['regenerated']} "
          f"final_sources={s['final_sources']} llm_violations={s['llm_violations']}")
    for line in format_usage(s):
        print(line)


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llm", choices=["none", "fake", "openai"], default="none")
    parser.add_argument("--cases", nargs="*", help="ID ca, mặc định chạy tất cả")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                        help="trần số lần gọi model, dừng trước khi chạy nếu vượt")
    parser.add_argument("--yes", action="store_true", help="xác nhận gọi API thật (--llm openai)")
    parser.add_argument("--out", type=Path, help="ghi từng ca ra JSONL, ví dụ data/generation_runs/dev.jsonl")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    cases = load_cases(args.cases or None)
    client, before = None, None
    if args.llm == "fake":
        client, before = oracle_client()
    elif args.llm == "openai":
        calls = len(cases) * CALLS_PER_CASE
        client = real_client(calls, f"{len(cases)} ca × tối đa {CALLS_PER_CASE} lần (kể cả sinh lại)",
                             max_calls=args.max_calls, confirmed=args.yes)
        if client is None:
            return 2

    verifier_rows = check_verifier(cases, ResponseVerifier(demo_answer_key))
    print_verifier_report(verifier_rows, summarize_verifier(verifier_rows))
    rows = []
    if client is not None:
        rows = evaluate(cases, client, before, run_info(args.llm, client))
        print_generation_report(rows, summarize(rows))
    if args.out and rows:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nĐã ghi {len(rows)} dòng vào {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
