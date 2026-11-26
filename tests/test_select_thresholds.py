"""Công cụ chọn ngưỡng mastery trên dev (plan §18.2): ứng viên, tính lại readiness, cùng ngân sách, không dùng test."""
import dataclasses
from fractions import Fraction
from itertools import combinations_with_replacement
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decision import SkillState  # noqa: E402
from app.agent.mastery import THRESHOLDS, standing, threshold, thresholds_override  # noqa: E402
from app.agent.rule_policy import compute_readiness  # noqa: E402
from research.agent.scenarios import load_scenarios  # noqa: E402
from research.evaluation import select_thresholds as tool  # noqa: E402

SCENARIOS = {sc.id: sc for sc in load_scenarios()}


def with_window(sc, window, view="recent_ratio"):
    """State của tình huống với skill mục tiêu có cửa sổ observation ``window``, không còn giả thuyết lỗi mở."""
    s = sc.state
    target = s.current.target_skill_id
    skill = SkillState(skill_id=target, independent_observations=len(window), recent_independent=list(window))
    skills = [k for k in s.skills if k.skill_id != target] + [skill]
    return s.model_copy(update={"skills": skills, "hypotheses": [], "mastery_view": view})


# --------------------------------------------------------------------------- ứng viên

def test_ratio_values_cover_every_window_size_not_only_fifths():
    values = tool.ratio_values()
    for v in ("1/2", "1/3", "2/3", "1/4", "3/4", "1/5", "4/5", "0", "1"):
        assert Fraction(v) in values
    assert len(values) == 11


def test_equivalent_threshold_sets_give_the_same_policy_inputs_in_the_real_code():
    """Hai bộ có cùng ``classification`` trên mọi cửa sổ thì ``standing`` và ``compute_readiness`` thật cho
    cùng kết quả trên mọi cửa sổ: khử trùng không bỏ mất cách phân loại nào."""
    base = SCENARIOS["SC-10"]
    states = [(w, with_window(base, w)) for w in tool.windows()]
    triples = [tuple(float(v) for v in t) for t in combinations_with_replacement(tool.ratio_values(), 3)]
    seen: dict[tuple, tuple] = {}
    for triple in triples:
        with thresholds_override("recent_ratio", dict(zip(tool.NAMES, triple))):
            real = tuple((standing(s, s.current.target_skill_id), compute_readiness(s).ready_to_advance)
                         for _, s in states)
        key = tuple(tool.classification(triple, w) for w, _ in states)
        assert seen.setdefault(key, real) == real, triple
    assert len(seen) == len(tool.ratio_candidates())


def test_both_estimates_get_the_same_number_of_candidates_and_keep_the_start():
    pool = tool.candidates()
    assert len(pool["bkt"]) == len(pool["recent_ratio"])
    for view in tool.VIEWS:
        assert tool.START[view] in pool[view] and len(set(pool[view])) == len(pool[view])
        assert all(low <= good <= ready for low, good, ready in pool[view])


# --------------------------------------------------------------------------- ngưỡng tạm

def test_an_override_only_lasts_inside_its_block():
    s = SCENARIOS["SC-01"].state.model_copy(update={"mastery_view": "recent_ratio"})
    with thresholds_override("recent_ratio", {"low": 0.2, "good": 0.5, "ready": 0.75}):
        assert threshold(s, "ready") == 0.75 and threshold(s.model_copy(update={"mastery_view": "bkt"}), "ready") == 0.8
    assert threshold(s, "ready") == THRESHOLDS["recent_ratio"]["ready"]
    with pytest.raises(ValueError):
        with thresholds_override("recent_ratio", {"low": 0.2}):
            pass


def test_readiness_is_recomputed_for_each_threshold_set_not_read_from_the_scenario():
    sc = SCENARIOS["SC-10"]  # học sinh tự giải đúng
    state = with_window(sc, (False, True, False, True, True))  # 3/5, hai lần gần nhất đúng
    stored = state.readiness.model_copy(update={"ready_to_advance": True, "unmet": []})
    sc = dataclasses.replace(sc, state=state.model_copy(update={"readiness": stored, "mastery_view": "bkt"}))
    assert tool.decide(sc, "recent_ratio", (0.4, 0.6, 0.6))["ready_to_advance"] is True
    assert tool.decide(sc, "recent_ratio", (0.4, 0.6, 0.8))["ready_to_advance"] is False


# --------------------------------------------------------------------------- độ nhạy

def test_a_change_of_the_probed_skill_counts_as_a_changed_decision():
    """Ca từ review: thêm một skill nền yếu vào SC-15, ngưỡng low đổi skill được kiểm tra mà action,
    intent và mức hint giữ nguyên."""
    sc = SCENARIOS["SC-15"]
    collect = SkillState(skill_id="SK-A03-COLLECT", p_mastery=0.1, independent_observations=3,
                         recent_independent=[False, False, False])
    sc = dataclasses.replace(sc, state=sc.state.model_copy(update={"skills": [*sc.state.skills, collect]}))
    rows = tool.evaluate([sc], "bkt", [tool.START["bkt"], (0.2, 0.6, 0.8)])
    start, low = (r["decisions"][0] for r in rows)
    assert (start["action"], start["intent"], start["hint_level"]) == (low["action"], low["intent"], low["hint_level"])
    assert start["target_skill_id"] != low["target_skill_id"] and low["target_skill_id"] == "SK-A03-COLLECT"
    assert rows[1]["changed_from_start"] == {"action": 0, "decision": 1}
    s = tool.select(rows)
    assert s["sensitive_scenarios"] == {"action": [], "decision": ["SC-15"]}
    assert s["per_scenario"]["SC-15"]["target_skills"] == sorted({start["target_skill_id"], "SK-A03-COLLECT"})


# --------------------------------------------------------------------------- dữ liệu đầu vào

def test_the_input_fingerprint_covers_the_loaded_state_and_every_source_file():
    sources = [tool.CONTRACTS / "fixtures.v1.json", tool.CONTRACTS / "scenarios.dev.v1.json"]
    first = tool.input_fingerprint(load_scenarios(), sources)
    assert first == tool.input_fingerprint(load_scenarios(), sources)  # tái lập được
    assert set(first["source_files"]) == {"contracts/agent/fixtures.v1.json", "contracts/agent/scenarios.dev.v1.json"}
    assert all(len(h) == 64 for h in first["source_files"].values()) and len(first["loaded_sha256"]) == 64
    # Một chỗ sửa trong state ghép từ fixture (cùng ID, cùng phiên bản policy) vẫn đổi hash.
    changed = [dataclasses.replace(sc, state=sc.state.model_copy(update={"state_version": sc.state.state_version + 1}))
               if sc.id == "SC-01" else sc for sc in load_scenarios()]
    assert tool.input_fingerprint(changed, sources)["loaded_sha256"] != first["loaded_sha256"]


# --------------------------------------------------------------------------- chọn

def test_ties_are_reported_and_broken_towards_the_start():
    rows, selection = tool.run([SCENARIOS["SC-01"], SCENARIOS["SC-10"]])
    assert {r["view"] for r in rows} == set(tool.VIEWS)
    for view, s in selection.items():
        if s["tied_with_selected"] == s["candidates"]:  # dev không phân biệt được bộ nào
            assert s["selected"]["thresholds"] == dict(zip(tool.NAMES, tool.START[view]))
        assert s["start"]["errors"] == 0


def test_the_test_split_is_refused():
    sc = dataclasses.replace(SCENARIOS["SC-01"], split="test")
    with pytest.raises(ValueError, match="dev only"):
        tool.run([sc])
