"""Phần dùng chung của các script đánh giá có gọi LLM: đọc cấu hình, xin xác nhận trước khi gọi
API thật, và thống kê token/latency/chi phí.

Quy ước: không script nào gọi API tính phí nếu thiếu ``--yes``; số lần gọi dự kiến được in trước.
"""
from __future__ import annotations

import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.llm.client import LLMDisabled, LLMSettings, OpenAIResponsesClient  # noqa: E402

DEFAULT_MAX_CALLS = 50


def read_env(path: Path = ROOT / ".env") -> dict[str, str]:
    """Biến trong ``.env`` (nếu có), bị biến môi trường ghi đè. Không in giá trị nào."""
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return {**values, **os.environ}


def real_client(calls: int, description: str, *, max_calls: int, confirmed: bool) -> OpenAIResponsesClient | None:
    """Client OpenAI thật, hoặc None (kèm lý do in ra stderr) nếu chưa đủ điều kiện để gọi."""
    try:
        settings = LLMSettings.from_env(read_env())
    except LLMDisabled as error:
        print(f"Không gọi API: {error}. Điền OPENAI_API_KEY và đặt LLM_ENABLED=true trong .env.", file=sys.stderr)
        return None
    print(f"Sẽ gọi {settings.model} tối đa {calls} lần ({description}), timeout {settings.timeout_seconds}s mỗi lần.")
    if calls > max_calls:
        print(f"Vượt --max-calls={max_calls}; dừng.", file=sys.stderr)
        return None
    if not confirmed:
        print("Thêm --yes để xác nhận gọi API thật.", file=sys.stderr)
        return None
    return OpenAIResponsesClient(settings)


def timing_stats(values: list[float]) -> dict:
    if not values:
        return {"median": None, "p95": None}
    ordered = sorted(values)
    return {"median": statistics.median(ordered),
            "p95": ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]}


def format_ms(stats: dict) -> str:
    return "-" if stats["median"] is None else f"median={stats['median']:.1f} p95={stats['p95']:.1f}"


def usage_summary(usages: list[dict]) -> dict:
    """Thống kê các lần gọi LLM (``LLMUsage`` đã dump thành dict).

    Token chỉ tính trên các lần provider trả usage (``usage_known``); lần thiếu (timeout, lỗi mạng)
    được đếm riêng ở ``usage_missing``, không tính thành 0. ``cost_usd_known`` là tổng của
    ``cost_known_calls`` / ``llm_calls`` lần gọi; hai số khác nhau nghĩa là chi phí thật có thể cao hơn."""
    known = [u for u in usages if u["input_tokens"] is not None]
    costs = [u["cost_usd"] for u in usages if u["cost_usd"] is not None]
    return {
        "llm_calls": len(usages),
        "api_ms": timing_stats([u["latency_ms"] for u in usages]),
        "usage_known": len(known),
        "usage_missing": len(usages) - len(known),
        "input_tokens_mean": statistics.mean(u["input_tokens"] for u in known) if known else None,
        "cached_input_tokens_total": sum(u["cached_input_tokens"] for u in known),
        "output_tokens_mean": statistics.mean(u["output_tokens"] for u in known) if known else None,
        "cost_known_calls": len(costs),
        "cost_usd_known": round(sum(costs), 6) if costs else None,
    }


def format_usage(s: dict) -> list[str]:
    """Các dòng báo cáo cho ``usage_summary``; rỗng nếu không có lần gọi nào."""
    if not s["llm_calls"]:
        return []
    tokens = (f"input_tokens_mean={s['input_tokens_mean']:.0f} cached_total={s['cached_input_tokens_total']} "
              f"output_tokens_mean={s['output_tokens_mean']:.0f}") if s["usage_known"] else "tokens=-"
    return [f"    llm_calls={s['llm_calls']} api_ms {format_ms(s['api_ms'])} usage_known={s['usage_known']} "
            f"usage_missing={s['usage_missing']} {tokens}",
            f"    cost_usd_known={s['cost_usd_known']} (from {s['cost_known_calls']}/{s['llm_calls']} calls)"]
