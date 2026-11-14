"""Usage contract shared by Agent and extraction."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMUsage(BaseModel):
    """Chi phí một lần gọi LLM (plan §18: latency/cost). Dùng chung cho Agent đề xuất và LLM
    extraction; tạo bằng ``app.llm.client.usage_from_call`` / ``usage_from_failure``.

    Ghi cả khi lần gọi lỗi (``error``): lượt đó vẫn tốn thời gian và có thể tốn token.
    ``model_id`` là tên model provider trả về (thường kèm ngày snapshot), không phải tên cấu hình.
    Số token để null khi provider không trả ``usage`` (timeout, lỗi mạng): không biết, khác với 0.
    ``cost_usd`` để null khi chưa biết số token hoặc model không có trong bảng giá ``price_version``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model_id: Annotated[str, Field(min_length=1, max_length=80)]
    prompt_version: Annotated[str, Field(min_length=1, max_length=40)]
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    price_version: str | None = None
    error: Annotated[str, Field(max_length=120)] | None = None

    @property
    def tokens_known(self) -> bool:
        return None not in (self.input_tokens, self.cached_input_tokens, self.output_tokens)

    @model_validator(mode="after")
    def _tokens(self):
        known = [self.input_tokens, self.cached_input_tokens, self.output_tokens]
        if any(v is None for v in known) and any(v is not None for v in known):
            raise ValueError("token counts are either all known or all null")
        if self.tokens_known and self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        if (self.cost_usd is None) != (self.price_version is None):
            raise ValueError("cost_usd and price_version go together")
        if self.cost_usd is not None and not self.tokens_known:
            raise ValueError("cost_usd needs known token counts")
        return self
