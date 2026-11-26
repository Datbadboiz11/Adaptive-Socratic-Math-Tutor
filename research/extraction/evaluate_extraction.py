"""Đo LLM extraction trên bộ ca dev: tách đúng bước, hỏi lại đúng lúc, và không sửa bài làm.

    python research/extraction/evaluate_extraction.py                      # chỉ luật, không gọi API
    python research/extraction/evaluate_extraction.py --llm fake           # LLM giả trung thành (oracle), không gọi API
    python research/extraction/evaluate_extraction.py --llm openai --yes   # GỌI API THẬT, tốn phí

Mỗi ca chạy qua đúng ``StepExtractor`` của hệ thống (luật → LLM → chốt chặn). LLM chỉ được gọi cho
ca mà luật không tự tách được, nên số lần gọi thật ít hơn số ca. ``--llm openai`` cần
``LLM_ENABLED=true`` và ``OPENAI_API_KEY`` trong ``.env``; script in số lần gọi tối đa rồi mới chạy,
và dừng nếu thiếu ``--yes``. Kết quả thô ghi bằng ``--out`` vào ``data/`` (đã ignore).

Đây là bộ dev tự soạn để phát triển prompt và luật, không phải test chính thức (plan §11.5, §19.3).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.llm.fakes import FakeLLMClient  # noqa: E402
from app.extraction.contracts import FIDELITY_REASONS  # noqa: E402
from app.extraction.extractor import EXTRACTOR_VERSION, PROMPT_VERSION, StepExtractor  # noqa: E402
from app.extraction.grammar import GRAMMAR_VERSION  # noqa: E402
from research.llm_support import DEFAULT_MAX_CALLS, format_usage, real_client, usage_summary  # noqa: E402

CASES_PATH = ROOT / "contracts" / "extraction" / "cases.dev.v1.json"


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    problem_prompt: str
    lines: tuple[str, ...]
    needs_llm: bool
    oracle: dict | None  # đầu ra của một LLM trung thành; None với ca không cần LLM
    status: str
    steps: tuple[str, ...]
    restated: bool
    reasons: frozenset[str]


@lru_cache(maxsize=1)
def _file() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def load_cases(ids: list[str] | None = None) -> list[Case]:
    data = _file()
    wanted = set(ids) if ids else None
    out = []
    for c in data["cases"]:
        if wanted is not None and c["id"] not in wanted:
            continue
        expected = c["expected"]
        out.append(Case(id=c["id"], title=c["title"], problem_prompt=data["problems"][c["problem"]],
                        lines=tuple(c["lines"]), needs_llm=c["needs_llm"], oracle=c.get("oracle"),
                        status=expected["status"], steps=tuple(expected["steps"]), restated=expected["restated"],
                        reasons=frozenset(expected["reasons"])))
    if wanted is not None and len(out) != len(wanted):
        raise KeyError(f"unknown case ids: {sorted(wanted - {c.id for c in out})}")
    return out


# --------------------------------------------------------------------------- chạy

def run_info(llm_mode: str, client=None) -> dict:
    """Phiên bản và cấu hình của lần chạy, ghi vào từng dòng kết quả để tái lập (NFR-04)."""
    data = _file()
    return {"extractor_version": EXTRACTOR_VERSION, "prompt_version": PROMPT_VERSION,
            "grammar_version": GRAMMAR_VERSION, "llm": llm_mode, "model": getattr(client, "model", None),
            "cases_file": CASES_PATH.name, "cases_split": data["split"]}


def run_case(case: Case, extractor: StepExtractor, run: dict | None = None) -> dict:
    outcome = extractor(case.problem_prompt, list(case.lines))
    result = outcome.result
    reasons = {r.value for r in result.reasons}
    restated = bool(result.steps) and result.steps[0].role == "restated_problem"
    extracted = result.status == "extracted"
    return {
        "case": case.id, "title": case.title, "expected_status": case.status, "status": result.status,
        "method": result.method, "steps": result.graded_lines(), "reasons": sorted(reasons),
        "llm_called": outcome.usage is not None,
        "status_ok": result.status == case.status,
        "exact": (result.status == case.status and tuple(result.graded_lines()) == case.steps
                  and restated == case.restated and reasons == case.reasons),
        # Chốt chặn đã can thiệp: LLM định sửa, cắt hoặc bỏ sót bài làm và bị chặn lại.
        "fidelity_block": bool(reasons & {r.value for r in FIDELITY_REASONS}),
        # Ca lọt: hệ thống đưa sang chấm các bước khác với đáp án của ca (hoặc lẽ ra phải hỏi lại).
        # Đây là lỗi nguy hiểm nhất, và chỉ đo được trên ca có đáp án như bộ này.
        "silent_change": extracted and (case.status != "extracted" or tuple(result.graded_lines()) != case.steps),
        "llm_output": outcome.llm_output,
        "usage": outcome.usage.model_dump(mode="json") if outcome.usage else None,
        "result": result.model_dump(mode="json"),
        "run": run,
    }


def evaluate(cases: list[Case], client=None, before_case=None, run: dict | None = None) -> list[dict]:
    """``before_case(case)`` cho phép nạp đầu ra cho LLM giả trước mỗi ca."""
    extractor = StepExtractor(client)
    rows = []
    for case in cases:
        if before_case is not None:
            before_case(case)
        rows.append(run_case(case, extractor, run))
    return rows


def oracle_client() -> tuple[FakeLLMClient, Callable[[Case], None]]:
    """LLM giả trả đúng ``oracle`` của ca: kiểm tra đường LLM (prompt, schema, chốt chặn, log) mà
    không tốn API. Kết quả của nó KHÔNG phản ánh chất lượng của model thật."""
    client = FakeLLMClient()

    def before_case(case: Case) -> None:
        client.outputs.clear()
        if case.oracle is not None:
            client.push(case.oracle)

    return client, before_case


# --------------------------------------------------------------------------- tổng hợp

def summarize(rows: list[dict]) -> dict:
    asked = [r for r in rows if r["status"] == "needs_clarification"]
    should_ask = [r for r in rows if r["expected_status"] == "needs_clarification"]
    right_asks = sum(r["expected_status"] == "needs_clarification" for r in asked)
    return {
        "cases": len(rows),
        "status_ok": sum(r["status_ok"] for r in rows),
        "exact": sum(r["exact"] for r in rows),
        "by_rules": sum(not r["llm_called"] for r in rows),
        # Trong các lần hệ thống hỏi lại, bao nhiêu lần là đúng; trong các ca cần hỏi lại, bắt được bao nhiêu.
        "clarification_precision": right_asks / len(asked) if asked else None,
        "clarification_recall": right_asks / len(should_ask) if should_ask else None,
        "fidelity_blocks": sum(r["fidelity_block"] for r in rows),
        "silent_changes": sum(r["silent_change"] for r in rows),
        **usage_summary([r["usage"] for r in rows if r["usage"]]),
    }


def _ratio(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def print_report(rows: list[dict], summary: dict) -> None:
    print(f"{'case':6} {'ok':3} {'status':20} {'by':5} {'llm':3}  steps / reasons")
    for r in rows:
        detail = " | ".join(r["steps"]) if r["status"] == "extracted" else ",".join(r["reasons"])
        print(f"{r['case']:6} {'yes' if r['exact'] else 'NO ':3} {r['status']:20} {r['method']:5} "
              f"{'yes' if r['llm_called'] else '-':3}  {detail}")
    s = summary
    print(f"\ncases={s['cases']} exact={s['exact']} status_ok={s['status_ok']} by_rules={s['by_rules']} "
          f"clarification_precision={_ratio(s['clarification_precision'])} "
          f"clarification_recall={_ratio(s['clarification_recall'])} fidelity_blocks={s['fidelity_blocks']} "
          f"silent_changes={s['silent_changes']}")
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
    parser.add_argument("--out", type=Path, help="ghi từng ca ra JSONL, ví dụ data/extraction_runs/dev.jsonl")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    cases = load_cases(args.cases or None)
    client, before = None, None
    if args.llm == "none":
        # Không có LLM thì ca cần LLM chắc chắn bị hỏi lại (mixed_text): chỉ đo phần luật.
        skipped = sum(c.needs_llm for c in cases)
        cases = [c for c in cases if not c.needs_llm]
        print(f"Chỉ chạy luật: bỏ qua {skipped} ca cần LLM.")
    elif args.llm == "fake":
        client, before = oracle_client()
    else:
        calls = sum(c.needs_llm for c in cases)
        client = real_client(calls, f"{calls}/{len(cases)} ca cần LLM", max_calls=args.max_calls, confirmed=args.yes)
        if client is None:
            return 2

    rows = evaluate(cases, client, before, run_info(args.llm, client))
    print_report(rows, summarize(rows))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nĐã ghi {len(rows)} dòng vào {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
