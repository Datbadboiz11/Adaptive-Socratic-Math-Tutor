"""Đồ giả cho test và lần chạy thử không tốn API. Không dùng trong luồng dạy thật.

- ScriptedProposer: Agent giả trả lần lượt các đề xuất định sẵn.
- FakeLLMClient: LLM giả cùng giao diện ``llm.LLMClient``, không gọi mạng.

Khác với ``stubs.py``: stub tạm thay phần của Member 1/2 và là mặc định của graph cho tới khi
có bản thật; đồ giả ở đây chỉ để kiểm thử phần của Agent.
"""
from __future__ import annotations

import json
from typing import Iterable

from app.agent.decide import ProposalOutcome
from app.agent.decision import DecisionProposal, DecisionSource, StudentState
from app.agent.llm import LLMCall
from app.agent.rule_policy import rule_policy
from app.agent.tools import TurnContext


class ScriptedProposer:
    """Agent giả cho test: trả lần lượt các đề xuất định sẵn.

    Mỗi phần tử là DecisionProposal, dict (được validate, lỗi thì thành agent_schema_error),
    một Exception để raise, hoặc None để dùng Rule-policy làm đề xuất của Agent."""

    def __init__(self, items: Iterable):
        self.items = list(items)
        self.seen_states: list[StudentState] = []

    def __call__(self, state: StudentState, ctx: TurnContext) -> ProposalOutcome:
        self.seen_states.append(state)
        item = self.items.pop(0) if self.items else None
        if isinstance(item, Exception):
            raise item
        if item is None:
            item = rule_policy(state, ctx)
        if isinstance(item, dict):
            item = DecisionProposal.model_validate(item)
        return ProposalOutcome(item, DecisionSource.AGENT)


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
