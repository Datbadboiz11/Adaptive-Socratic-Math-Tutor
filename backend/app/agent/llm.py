"""Lớp gọi LLM cho Agent: cấu hình, client OpenAI (Responses API, structured output) và giá.

Không có lệnh gọi mạng nào khi import module này. Client thật chỉ được tạo khi cấu hình bật
rõ ràng (``LLM_ENABLED=true`` và có ``OPENAI_API_KEY``); test dùng client giả trong ``stubs.py``.

Chính sách gọi (plan §13: lỗi thì fallback, không thử lại vô hạn):
- ``max_retries=0`` và timeout cứng: lỗi hay chậm thì Agent rơi về Rule-policy ngay trong lượt.
- ``store=False``: không lưu hội thoại phía provider.
- Không gửi định danh học sinh; ``build_input`` chỉ gửi state đã chiếu theo cấu hình.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
from typing import Mapping, Protocol

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_OUTPUT_TOKENS = 400

# Giá niêm yết USD / 1M token. Đối chiếu lại trang giá OpenAI trước khi báo cáo chi phí;
# đổi giá thì đổi cả PRICE_VERSION để bản ghi cũ vẫn truy được bảng giá đã dùng.
PRICE_VERSION = "openai-list-2026-11-14"


@dataclass(frozen=True)
class Price:
    input: float
    cached_input: float
    output: float


PRICES: dict[str, Price] = {
    "gpt-4o-mini": Price(input=0.15, cached_input=0.075, output=0.60),
}


def price_for(model_id: str) -> Price | None:
    """Giá theo tên model; tên snapshot (``gpt-4o-mini-2024-07-18``) dùng giá của tên gốc."""
    for name in sorted(PRICES, key=len, reverse=True):
        if model_id == name or model_id.startswith(name + "-"):
            return PRICES[name]
    return None


def cost_usd(model_id: str, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float | None:
    price = price_for(model_id)
    if price is None:
        return None
    fresh = input_tokens - cached_input_tokens
    total = fresh * price.input + cached_input_tokens * price.cached_input + output_tokens * price.output
    return round(total / 1_000_000, 8)


# --------------------------------------------------------------------------- cấu hình

class LLMDisabled(RuntimeError):
    """Cấu hình chưa cho phép gọi model (tắt, hoặc thiếu key)."""


@dataclass(frozen=True)
class LLMSettings:
    model: str = DEFAULT_MODEL
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    temperature: float = 0.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "LLMSettings":
        """Đọc ``LLM_ENABLED``, ``OPENAI_API_KEY``, ``OPENAI_MODEL``, ``AGENT_LLM_TIMEOUT_SECONDS``.

        Raise ``LLMDisabled`` thay vì âm thầm chạy Rule-policy: cấu hình Agent mà không gọi
        được model thì kết quả thí nghiệm sẽ sai nhãn."""
        if env.get("LLM_ENABLED", "false").strip().lower() != "true":
            raise LLMDisabled("LLM_ENABLED is not true")
        provider = env.get("LLM_PROVIDER", "openai").strip().lower()
        if provider != "openai":
            raise LLMDisabled(f"unsupported LLM_PROVIDER: {provider}")
        key = env.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise LLMDisabled("OPENAI_API_KEY is empty")
        timeout = float(env.get("AGENT_LLM_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
        if not 0 < timeout <= 60:
            raise ValueError("AGENT_LLM_TIMEOUT_SECONDS must be in (0, 60]")
        return cls(model=env.get("OPENAI_MODEL", "").strip() or DEFAULT_MODEL, api_key=key,
                   timeout_seconds=timeout)


# --------------------------------------------------------------------------- client

@dataclass(frozen=True)
class LLMCall:
    """Kết quả thô một lần gọi. ``text`` là None khi model từ chối hoặc trả về dở dang.
    Số token là None khi provider không trả ``usage``."""

    text: str | None
    model_id: str
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    refusal: str | None = None
    incomplete_reason: str | None = None


class LLMTimeout(TimeoutError):
    def __init__(self, latency_ms: float):
        super().__init__(f"LLM call timed out after {latency_ms:.0f} ms")
        self.latency_ms = latency_ms


class LLMCallFailed(RuntimeError):
    """Lỗi provider (mạng, xác thực, rate limit...). Giữ latency để vẫn ghi được chi phí lượt."""

    def __init__(self, kind: str, latency_ms: float):
        super().__init__(kind)
        self.kind = kind
        self.latency_ms = latency_ms


class LLMClient(Protocol):
    model: str

    def complete_json(self, *, instructions: str, input: str, schema_name: str, schema: dict) -> LLMCall:
        """Một lần gọi, đầu ra ràng buộc theo JSON Schema (strict)."""


class OpenAIResponsesClient:
    """Gọi OpenAI Responses API với structured output strict. ``sdk`` để test truyền client giả."""

    def __init__(self, settings: LLMSettings, sdk=None):
        self.settings = settings
        self.model = settings.model
        if sdk is None:
            from openai import OpenAI  # import muộn: môi trường không dùng LLM không cần package

            sdk = OpenAI(api_key=settings.api_key, timeout=settings.timeout_seconds, max_retries=0)
        self._sdk = sdk

    def complete_json(self, *, instructions: str, input: str, schema_name: str, schema: dict) -> LLMCall:
        import openai

        started = time.perf_counter()
        try:
            response = self._sdk.responses.create(
                model=self.settings.model, instructions=instructions, input=input, store=False,
                temperature=self.settings.temperature, max_output_tokens=self.settings.max_output_tokens,
                text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}})
        except openai.APITimeoutError:
            raise LLMTimeout(_elapsed(started)) from None
        except openai.OpenAIError as error:
            raise LLMCallFailed(type(error).__name__, _elapsed(started)) from None
        latency = _elapsed(started)

        usage = response.usage
        details = getattr(usage, "input_tokens_details", None) if usage else None
        refusal = next((part.refusal for item in (response.output or []) if getattr(item, "type", "") == "message"
                        for part in item.content if getattr(part, "type", "") == "refusal"), None)
        incomplete = response.incomplete_details.reason if response.incomplete_details else None
        text = None if (refusal or incomplete) else response.output_text
        # Không có usage thì không biết số token (để None, không phải 0). Có usage mà không có chi tiết
        # cache thì coi là không có token nào được cache.
        return LLMCall(text=text, model_id=response.model or self.settings.model,
                       input_tokens=usage.input_tokens if usage else None,
                       cached_input_tokens=((details.cached_tokens or 0) if details else 0) if usage else None,
                       output_tokens=usage.output_tokens if usage else None,
                       latency_ms=latency, refusal=refusal, incomplete_reason=incomplete)


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
