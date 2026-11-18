"""Chạy lại bộ dev hai lần trong các tiến trình nhỏ (plan §18.2).

    python research/evaluation/run_dev_repeat.py --out data/ablation/dev-repeat-fake
    python research/evaluation/run_dev_repeat.py --llm openai --yes --out data/ablation/dev-04

    python research/evaluation/run_dev_repeat.py --llm openai --yes --out data/ablation/dev-04 --resume

Mỗi phần chạy cùng run_ablation.py. Chỉ gộp khi đủ mọi cặp tình huống/cấu hình/lần lặp,
phiên bản khớp và mã nguồn không đổi. Ghi riêng lỗi API, đề xuất probe và lỗi hỏi dồn.

Lô bị ngắt giữa chừng thì chạy lại cùng lệnh với ``--resume``: phần đã xong được dùng lại, không gọi
model lần hai; phần dở được chạy lại vào thư mục mới (``part-3-retry1``), thư mục dở vẫn giữ nguyên.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.llm.client import LLMDisabled, LLMSettings  # noqa: E402
from research.agent.scenarios import load_scenarios  # noqa: E402
from research.evaluation.run_ablation import (  # noqa: E402
    CONFIGURATIONS, max_calls, print_report, run_info, summarize, system_outputs,
)
from research.llm_support import read_env  # noqa: E402

REPEAT = 2
PART_SIZE = 4
# Trần của lô: 16 tình huống × 2 lần × (5 lượt gọi Agent + 7 cấu hình × 2 lần sinh câu).
MAX_RUN_CALLS = 608
FATAL_API_ERRORS = frozenset({"APIConnectionError", "AuthenticationError", "PermissionDeniedError"})
# Phần nào cũng phải giống cả lô ở các trường này thì mới gộp được.
SHARED_RUN_FIELDS = ("llm", "model", "versions", "repeat", "configurations", "max_regenerations", "scenario_split")


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_hashes() -> dict[str, str]:
    paths = [Path(__file__), ROOT / "research/llm_support.py", ROOT / "content/curriculum/registry.v1.json"]
    for folder in ("backend/app/agent", "backend/app/generation", "backend/app/llm",
                   "research/agent", "research/evaluation"):
        paths.extend((ROOT / folder).glob("*.py"))
    paths.extend((ROOT / "contracts/agent").glob("*.json"))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def diagnostics(rows: list[dict]) -> dict:
    """Tách đề xuất của Agent khỏi quyết định cuối và đo lỗi ở từng lần sinh."""
    result = {}
    for config in CONFIGURATIONS:
        group = [r for r in rows if r["configuration"] == config]
        proposals = [r["decision"]["proposed"] for r in group if r.get("decision") and r["decision"]["proposed"]]
        drafts = [[a for a in r["attempts"] if a["source"] == "llm"] for r in group]
        failed_first = [a for a in drafts if a and "too_many_questions" in a[0]["violations"]]
        usages = [u for r in group for u in [r["agent_usage"], *r["generation_usages"]] if u]
        result[config] = {
            "runs": len(group), "parsed_agent_proposals": len(proposals),
            "proposed_probe": sum(p["intent"] == "probe_prerequisite" for p in proposals),
            "rejected_probe": sum(bool(r.get("decision")) and bool(r["decision"]["proposed"])
                                  and r["decision"]["proposed"]["intent"] == "probe_prerequisite"
                                  and r["gate"] == "rejected" for r in group),
            "final_probe": sum(r.get("final_intent") == "probe_prerequisite" for r in group),
            "first_generation_messages": sum(bool(a) and a[0]["message"] is not None for a in drafts),
            "first_too_many_questions": len(failed_first),
            "question_failures_fixed_on_retry": sum(len(a) > 1 and a[1]["accepted"] for a in failed_first),
            "question_failures_sent_template": sum(r.get("response_source") == "template_fallback"
                and any("too_many_questions" in a["violations"] for a in r["attempts"]) for r in group),
            "api_errors": dict(Counter(u["error"] for u in usages if u["error"])),
        }
    return result


def fatal_api_errors(rows: list[dict]) -> set[str]:
    return {error for config in diagnostics(rows).values() for error in config["api_errors"]} & FATAL_API_ERRORS


def finished_part(out: Path, number: int, scenario_ids: list[str], manifest: dict) -> Path | None:
    """Thư mục của phần này nếu một lần chạy trước đã xong và dùng lại được: đủ kết quả, cùng cấu
    hình với lô, không dính lỗi API làm dừng lô."""
    for part in (out / f"part-{number}", *sorted(out.glob(f"part-{number}-retry*"))):
        summary = part / "summary.json"
        if not summary.exists():
            continue
        info = json.loads(summary.read_text(encoding="utf-8"))["run"]
        same = info["scenarios"] == scenario_ids and all(info[f] == manifest["run"][f] for f in SHARED_RUN_FIELDS)
        if same and not fatal_api_errors(read_rows(part / "runs.jsonl")):
            return part
    return None


def new_part_folder(out: Path, number: int) -> Path:
    """Thư mục chưa tồn tại cho lần chạy tiếp của phần này; không ghi đè hay xóa lần chạy dở."""
    names = [f"part-{number}", *(f"part-{number}-retry{n}" for n in range(1, 100))]
    return next(out / name for name in names if not (out / name).exists())


def merge_parts(out: Path, manifest: dict, parts: list[Path]) -> None:
    rows = []
    for part in parts:
        info = json.loads((part / "summary.json").read_text(encoding="utf-8"))["run"]
        for field in SHARED_RUN_FIELDS:
            if info[field] != manifest["run"][field]:
                raise ValueError(f"{part}: inconsistent {field}")
        rows.extend(read_rows(part / "runs.jsonl"))
    expected = {(sc, config, attempt) for sc in manifest["run"]["scenarios"]
                for config in manifest["run"]["configurations"] for attempt in range(1, REPEAT + 1)}
    actual = [(r["scenario"], r["configuration"], r["attempt"]) for r in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Missing, duplicate or unexpected scenario/configuration/attempt")
    if source_hashes() != manifest["sha256"]:
        raise ValueError("Source changed during the run")
    rows.sort(key=lambda r: (r["attempt"], r["scenario"], manifest["run"]["configurations"].index(r["configuration"])))
    summary = summarize(rows)
    (out / "runs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (out / "outputs.jsonl").write_text("".join(o.model_dump_json() + "\n" for o in system_outputs(rows)), encoding="utf-8")
    write_json(out / "summary.json", {"run": manifest["run"], **summary})
    write_json(out / "diagnostics.json", diagnostics(rows))
    print_report(summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llm", choices=("fake", "openai"), default="fake")
    parser.add_argument("--yes", action="store_true",
                        help=f"xác nhận toàn bộ lô, tối đa {MAX_RUN_CALLS} lần gọi với 16 tình huống")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--resume", action="store_true", help="chạy tiếp lô đã có trong --out, dùng lại phần đã xong")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    resuming = (out / "manifest.json").exists()
    if resuming and not args.resume:
        parser.error(f"{out} already has a run; pass --resume to continue it")
    if not resuming and out.exists() and any(out.iterdir()):
        parser.error(f"{out} already has files")
    settings = None
    child_env = os.environ.copy()
    if args.llm == "openai":
        if not args.yes:
            parser.error("--llm openai requires --yes")
        try:
            child_env = read_env()
            settings = LLMSettings.from_env(child_env)
            socket.getaddrinfo("api.openai.com", 443)
        except (LLMDisabled, ValueError, OSError) as error:
            print(f"Preflight failed: {type(error).__name__}. Check LLM settings and DNS.", file=sys.stderr)
            return 2
    scenarios = load_scenarios()
    calls = max_calls(len(scenarios), list(CONFIGURATIONS), REPEAT)
    if calls > MAX_RUN_CALLS:
        parser.error(f"{calls} calls exceed this dev run's budget of {MAX_RUN_CALLS}")
    model = settings.model if settings else "fake-llm"
    manifest = {"run": run_info(args.llm, model, scenarios, list(CONFIGURATIONS), REPEAT),
                "max_calls": calls, "part_size": PART_SIZE,
                "sha256": source_hashes()}
    if settings:
        manifest["settings"] = {key: getattr(settings, key) for key in
                                ("model", "temperature", "max_output_tokens", "timeout_seconds")}
    if resuming:
        if json.loads((out / "manifest.json").read_text(encoding="utf-8")) != json.loads(json.dumps(manifest)):
            print("Cannot resume: source, scenarios or settings changed since this run started. "
                  "Start a new run in another folder.", file=sys.stderr)
            return 1
        if (out / "summary.json").exists():
            print(f"{out} is already complete; nothing to run.")
            return 0
    else:
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "manifest.json", manifest)
    parts = []
    for number, offset in enumerate(range(0, len(scenarios), PART_SIZE), start=1):
        subset = [sc.id for sc in scenarios[offset:offset + PART_SIZE]]
        part = finished_part(out, number, subset, manifest)
        if part is not None:
            print(f"Reusing {part.name}: {', '.join(subset)}", flush=True)
            parts.append(part)
            continue
        if source_hashes() != manifest["sha256"]:
            print("Source changed; stopped before the next part.", file=sys.stderr)
            return 1
        part = new_part_folder(out, number)
        command = [sys.executable, "-X", "utf8", "-u", str(ROOT / "research/evaluation/run_ablation.py"),
                   "--llm", args.llm, "--repeat", str(REPEAT), "--max-calls",
                   str(max_calls(len(subset), list(CONFIGURATIONS), REPEAT)), "--out", str(part),
                   "--scenarios", *subset]
        if args.yes:
            command.append("--yes")
        print(f"Running {part.name}: {', '.join(subset)}", flush=True)
        with (out / f"{part.name}.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, env=child_env, stdout=log, stderr=subprocess.STDOUT, check=False)
        # run_ablation trả mã 1 khi có lượt lỗi nhưng vẫn ghi đủ kết quả: lượt lỗi đi vào bản gộp và
        # được báo ở đó. Chỉ dừng khi phần này không chạy hết hoặc API không dùng được.
        if not (part / "summary.json").exists():
            print(f"Stopped at {part.name}; see its log and runs.jsonl. Run again with --resume.", file=sys.stderr)
            return 1
        if fatal_api_errors(read_rows(part / "runs.jsonl")):
            print(f"API unavailable in {part.name}; stopped. Run again with --resume.", file=sys.stderr)
            return 1
        parts.append(part)
    merge_parts(out, manifest, parts)
    print(f"Saved complete run to {out}")
    failed = json.loads((out / "summary.json").read_text(encoding="utf-8"))["errors"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
