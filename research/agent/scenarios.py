"""Đọc bộ tình huống dev của Agent (``contracts/agent/scenarios.dev.v1.json``).

State của mỗi tình huống = ``student_state`` trong ``fixtures.v1.json`` ghép đè bằng
``state_patch``; context = ``base_context`` ghép đè bằng ``context_patch``. Ghép sâu với dict,
list thì thay nguyên. Dùng chung cho test và script so sánh proposer.

``load_scenarios(path=...)`` đọc một split đã replay của bộ tình huống thích ứng
(``research/scenarios/build.py``): state ở đó dựng từ lịch sử, không ghép từ fixture.

Dữ liệu dev, không thuộc luồng dạy thật. Cần ``backend/`` trong ``sys.path`` (để import
``app.agent``), như các test và ``compare_proposers.py`` đã làm.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path

from app.agent.decision import StudentState
from app.agent.tools import ProblemRef, TurnContext
from research.scenarios.contracts import ScenarioSet, StrategyLabels

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
    expected_rule_action: str | None
    expected_rule_intent: str | None
    acceptable_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    state: StudentState
    context: TurnContext
    split: str = "dev"
    dataset_version: str | None = None
    problem_refs: dict[str, ProblemRef] = field(default_factory=dict)
    problem_prompts: dict[str, str] = field(default_factory=dict)
    # Nhãn chi tiết của bộ đã replay (intent, skill cần hướng tới); None với bộ 16 tình huống cũ.
    labels: StrategyLabels | None = None

    def detail_acceptable(self, action: str, intent: str | None, target_skill_id: str | None) -> bool | None:
        """Quyết định có khớp nhãn ở mức intent/skill không; None khi tình huống không có nhãn chi tiết."""
        if self.labels is None or not self.labels.has_detail:
            return None
        return self.labels.accepts(action, intent, target_skill_id)


def scenario_file() -> dict:
    return copy.deepcopy(_files()[1])


def load_scenarios(ids: list[str] | None = None, *, path: Path | None = None) -> list[Scenario]:
    if path is not None:
        return _load_replayed(path, ids)
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


def _load_replayed(path: Path, ids: list[str] | None) -> list[Scenario]:
    data = ScenarioSet.model_validate_json(path.read_text(encoding="utf-8-sig"))
    wanted = set(ids) if ids else {s.scenario_id for s in data.scenarios}
    if missing := wanted - {s.scenario_id for s in data.scenarios}:
        raise KeyError(f"unknown scenario ids: {sorted(missing)}")
    return [Scenario(id=s.scenario_id, title=s.title, expected_rule_action=None, expected_rule_intent=None,
                     acceptable_actions=tuple(s.labels.acceptable_actions), forbidden_actions=tuple(s.labels.forbidden_actions),
                     state=s.state, context=s.context, split=data.split, dataset_version=data.dataset_version,
                     problem_refs={p.problem.problem_id: p.problem for p in data.problems},
                     problem_prompts={p.problem.problem_id: p.prompt for p in data.problems}, labels=s.labels)
            for s in data.scenarios if s.scenario_id in wanted]
