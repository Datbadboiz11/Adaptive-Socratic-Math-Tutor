"""Fake LLM client for tests and offline experiments."""
from __future__ import annotations

import json
from typing import Iterable

from app.llm.client import LLMCall


class FakeLLMClient:
    """LLM giả cùng giao diện ``llm.LLMClient``; không gọi mạng.

    Mỗi phần tử của ``outputs`` là chuỗi (đầu ra thô của model), dict (được đổi thành JSON),
    ``LLMCall`` (trả nguyên) hoặc Exception (để raise). Số token ước lượng 4 ký tự/token để
    phần đo chi phí có số liệu khác 0; ``model`` mặc định không có trong bảng giá."""

    def __init__(self, outputs: Iterable = (), model: str = "fake-llm"):
        self.outputs = list(outputs)
        self.model = model
        self.requests: list[dict] = []

    def push(self, output) -> None:
        self.outputs.append(output)

    def complete_json(self, *, instructions: str, input: str, schema_name: str, schema: dict) -> LLMCall:
        self.requests.append({"instructions": instructions, "input": input, "schema_name": schema_name,
                              "schema": schema})
        if not self.outputs:
            raise AssertionError("FakeLLMClient has no output left")
        item = self.outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMCall):
            return item
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return LLMCall(text=text, model_id=self.model, input_tokens=(len(instructions) + len(input)) // 4,
                       cached_input_tokens=0, output_tokens=len(text) // 4, latency_ms=0.0)
