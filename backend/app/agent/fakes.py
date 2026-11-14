"""Scripted Agent proposer for tests and offline experiments."""
from __future__ import annotations

from typing import Iterable

from app.agent.decide import ProposalOutcome
from app.agent.decision import DecisionProposal, DecisionSource, StudentState
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
