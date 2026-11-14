"""Đọc bộ tình huống dev của Agent (``contracts/agent/scenarios.dev.v1.json``).

State của mỗi tình huống = ``student_state`` trong ``fixtures.v1.json`` ghép đè bằng
``state_patch``; context = ``base_context`` ghép đè bằng ``context_patch``. Ghép sâu với dict,
list thì thay nguyên. Dùng chung cho test và script so sánh proposer.

Dữ liệu dev, không thuộc luồng dạy thật. Cần ``backend/`` trong ``sys.path`` (để import
``app.agent``), như các test và ``compare_proposers.py`` đã làm.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from app.agent.decision import StudentState
from app.agent.tools import TurnContext

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts" / "agent"


def merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


@lru_cache(maxsize=1)
def _files() -> tuple[dict, dict]:
    fixtures = json.loads((CONTRACTS / "fixtures.v1.json").read_text(encoding="utf-8"))
    scenarios = json.loads((CONTRACTS / "scenarios.dev.v1.json").read_text(encoding="utf-8"))
    return fixtures, scenarios


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    expected_rule_action: str
    expected_rule_intent: str
    acceptable_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    state: StudentState
    context: TurnContext


def scenario_file() -> dict:
    return copy.deepcopy(_files()[1])


def load_scenarios(ids: list[str] | None = None) -> list[Scenario]:
    fixtures, data = _files()
    wanted = set(ids) if ids else None
    out = []
    for sc in data["scenarios"]:
        if wanted is not None and sc["id"] not in wanted:
            continue
        out.append(Scenario(
            id=sc["id"], title=sc["title"], expected_rule_action=sc["expected_rule_action"],
            expected_rule_intent=sc["expected_rule_intent"],
            acceptable_actions=tuple(sc["acceptable_actions"]), forbidden_actions=tuple(sc["forbidden_actions"]),
            state=StudentState.model_validate(merge(fixtures["student_state"], sc.get("state_patch", {}))),
            context=TurnContext.model_validate(merge(data["base_context"], sc.get("context_patch", {})))))
    if wanted is not None and len(out) != len(wanted):
        missing = sorted(wanted - {s.id for s in out})
        raise KeyError(f"unknown scenario ids: {missing}")
    return out
