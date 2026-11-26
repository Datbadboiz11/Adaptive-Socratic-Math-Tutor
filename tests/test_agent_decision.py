"""Hợp đồng quyết định sư phạm: bộ action chuẩn, ràng buộc hình dạng và fixtures."""
import copy
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent.decision import (  # noqa: E402
    ACTION_PRIORITY, ACTION_SPECS, CONTRACT_VERSION, INTENT_ACTION, DecisionIntent,
    DecisionProposal, PedagogicalAction, PedagogicalDecision, StudentState, priority,
)

FIXTURES = json.loads((ROOT / "contracts/agent/fixtures.v1.json").read_text(encoding="utf-8"))
CANONICAL_ACTIONS = {"clarify", "diagnose", "minimal_hint", "conceptual_question", "backtrack",
                     "scaffold", "check_transfer", "next_problem", "end_session"}


def proposal(**overrides):
    base = {"action": "minimal_hint", "intent": "prompt_self_check", "target_skill_id": "SK-A02-DISTRIBUTE",
            "hint_level": 1, "evidence": [{"kind": "assessment", "id": "a1"}], "reason": "Lỗi ở bước 1."}
    base.update(overrides)
    return base


def decision(case):
    return copy.deepcopy(next(d["decision"] for d in FIXTURES["decisions"] if d["case"] == case))


def test_action_set_matches_prd_fr10():
    assert {a.value for a in PedagogicalAction} == CANONICAL_ACTIONS
    assert set(ACTION_SPECS) == set(PedagogicalAction) == set(ACTION_PRIORITY)


def test_each_intent_belongs_to_exactly_one_action():
    owners = [a for spec in ACTION_SPECS.values() for a in spec.intents]
    assert len(owners) == len(set(owners)) == len(DecisionIntent)
    assert set(INTENT_ACTION) == set(DecisionIntent)


def test_hint_ladder_covers_levels_zero_to_four_without_gaps():
    levels = set().union(*(spec.hint_levels for spec in ACTION_SPECS.values()))
    assert levels == {0, 1, 2, 3, 4}
    assert ACTION_SPECS[PedagogicalAction.SCAFFOLD].hint_levels == {3, 4}


def test_priority_follows_clarify_diagnose_support_transfer_advance():
    p = ACTION_PRIORITY
    assert p[PedagogicalAction.CLARIFY] < p[PedagogicalAction.DIAGNOSE] < p[PedagogicalAction.MINIMAL_HINT]
    assert p[PedagogicalAction.MINIMAL_HINT] < p[PedagogicalAction.CHECK_TRANSFER] < p[PedagogicalAction.NEXT_PROBLEM]


def test_valid_minimal_hint():
    assert DecisionProposal.model_validate(proposal()).action == PedagogicalAction.MINIMAL_HINT


@pytest.mark.parametrize("overrides,code", [
    ({"intent": "independent_check"}, "S01_intent_not_allowed"),
    ({"hint_level": 3}, "S02_hint_level_not_allowed"),
    ({"target_skill_id": None}, "S03_target_skill_required"),
    ({"evidence": []}, "S04_evidence_required"),
    ({"action": "backtrack", "intent": "review_prerequisite", "hint_level": 0}, "S05_edge_ids_required"),
    ({"action": "diagnose", "intent": "probe_prerequisite", "hint_level": 0}, "S05_edge_ids_required"),
    ({"action": "check_transfer", "intent": "independent_check", "hint_level": 0}, "S06_problem_id_required"),
    ({"action": "scaffold", "intent": "analogous_example", "hint_level": 3}, "S07_content_ids_required"),
    ({"action": "end_session", "intent": "student_request", "hint_level": 0}, "S08_end_session_has_payload"),
    ({"content_ids": ["KB-1", "KB-1"]}, "S09_duplicate_content_ids"),
])
def test_structural_violations(overrides, code):
    with pytest.raises(ValidationError, match=code):
        DecisionProposal.model_validate(proposal(**overrides))


def test_hint_level_outside_ladder_rejected():
    with pytest.raises(ValidationError):
        DecisionProposal.model_validate(proposal(hint_level=5))


def test_agent_cannot_write_mastery_or_unknown_fields():
    with pytest.raises(ValidationError, match="extra"):
        DecisionProposal.model_validate(proposal(mastery_after=0.9))


def test_end_session_without_payload_is_valid():
    p = DecisionProposal.model_validate({"action": "end_session", "intent": "student_request",
                                         "reason": "Học sinh muốn dừng."})
    assert p.evidence == []


def test_fixture_state_validates():
    state = StudentState.model_validate(FIXTURES["student_state"])
    assert state.latest_assessment.misconception_candidate == "M_DIST_01"
    assert state.skill("SK-A02-DISTRIBUTE").independent_observations == 3


@pytest.mark.parametrize("case", [d["case"] for d in FIXTURES["decisions"]])
def test_fixture_decisions_validate(case):
    PedagogicalDecision.model_validate(decision(case))


def test_no_bkt_state_allows_missing_mastery():
    raw = copy.deepcopy(FIXTURES["student_state"])
    for skill in raw["skills"]:
        skill["p_mastery"] = None
    assert StudentState.model_validate(raw).skills[0].p_mastery is None


def test_state_rejects_deep_return_stack_and_duplicate_skills():
    raw = copy.deepcopy(FIXTURES["student_state"])
    frame = {"problem_id": "E02-P001", "opportunity_id": "44444444-4444-4444-8444-444444444444",
             "concept_id": "E02", "skill_id": "SK-E02-SOLVE", "hint_level": 1}
    raw["return_stack"] = [frame, frame, frame]
    with pytest.raises(ValidationError):
        StudentState.model_validate(raw)
    raw = copy.deepcopy(FIXTURES["student_state"])
    raw["skills"].append(copy.deepcopy(raw["skills"][0]))
    with pytest.raises(ValidationError, match="unique"):
        StudentState.model_validate(raw)


def test_accepted_gate_must_keep_proposal():
    raw = decision("accepted_conceptual_question")
    raw["final"]["hint_level"] = 2
    with pytest.raises(ValidationError, match="accepted proposal"):
        PedagogicalDecision.model_validate(raw)


def test_rejected_gate_requires_rules_and_fallback():
    raw = decision("gate_rejected_advance")
    raw["fallback_reason"] = "agent_error"
    with pytest.raises(ValidationError, match="gate_rejected"):
        PedagogicalDecision.model_validate(raw)
    raw = decision("gate_rejected_advance")
    raw["gate"]["violated_rules"] = []
    with pytest.raises(ValidationError, match="violated_rules"):
        PedagogicalDecision.model_validate(raw)


def test_missing_proposal_needs_agent_fallback_reason():
    raw = decision("agent_timeout_fallback")
    raw["fallback_reason"] = "gate_rejected"
    with pytest.raises(ValidationError, match="missing proposal"):
        PedagogicalDecision.model_validate(raw)


def test_rule_policy_configuration_has_no_agent_proposals():
    raw = decision("rule_policy_check_transfer")
    raw["proposed_by"] = "agent"
    raw["final_source"] = "agent"
    with pytest.raises(ValidationError, match="rule_policy"):
        PedagogicalDecision.model_validate(raw)


def test_rule_policy_configuration_has_no_agent_failures():
    # Lỗi cũ: nhánh proposal=None trả về sớm nên bỏ qua kiểm tra cấu hình rule_policy.
    raw = decision("agent_timeout_fallback")
    raw["config"]["configuration"] = "rule_policy"
    with pytest.raises(ValidationError, match="rule_policy"):
        PedagogicalDecision.model_validate(raw)
    raw["proposed_by"] = "rule_policy"
    with pytest.raises(ValidationError, match="rule_policy"):
        PedagogicalDecision.model_validate(raw)


def test_fallback_decision_must_pass_gate():
    raw = decision("gate_rejected_advance")
    del raw["fallback_gate"]
    with pytest.raises(ValidationError, match="fallback_gate"):
        PedagogicalDecision.model_validate(raw)
    raw = decision("gate_rejected_advance")
    raw["fallback_gate"] = {"status": "rejected", "violated_rules": ["G02_hint_jump"], "gate_version": "gate-0.1.0"}
    with pytest.raises(ValidationError, match="fallback decision must pass"):
        PedagogicalDecision.model_validate(raw)
    raw = decision("accepted_conceptual_question")
    raw["fallback_gate"] = {"status": "accepted", "violated_rules": [], "gate_version": "gate-0.1.0"}
    with pytest.raises(ValidationError, match="fallback_gate"):
        PedagogicalDecision.model_validate(raw)


def test_student_stop_request_overrides_pedagogical_priority():
    stop = priority(PedagogicalAction.END_SESSION, DecisionIntent.STUDENT_REQUEST)
    assert stop < priority(PedagogicalAction.CLARIFY, DecisionIntent.RESOLVE_INPUT)
    assert priority(PedagogicalAction.END_SESSION, DecisionIntent.BUDGET_EXHAUSTED) == stop
    assert priority(PedagogicalAction.END_SESSION, DecisionIntent.SESSION_GOAL_MET) == ACTION_PRIORITY[
        PedagogicalAction.END_SESSION]


def test_hypothesis_evidence_resolves_to_unique_hypothesis():
    state = StudentState.model_validate(FIXTURES["student_state"])
    ids = {h.hypothesis_id for h in state.hypotheses}
    for case in FIXTURES["decisions"]:
        for ref in case["decision"]["final"]["evidence"]:
            if ref["kind"] == "hypothesis":
                assert ref["id"] in ids
    raw = copy.deepcopy(FIXTURES["student_state"])
    raw["hypotheses"].append(copy.deepcopy(raw["hypotheses"][0]))
    with pytest.raises(ValidationError, match="hypothesis_id"):
        StudentState.model_validate(raw)


def test_contract_version_single_source():
    assert FIXTURES["contract_version"] == CONTRACT_VERSION
    assert StudentState.model_validate(FIXTURES["student_state"]).contract_version == CONTRACT_VERSION


def test_tool_budget_enforced():
    raw = decision("accepted_conceptual_question")
    raw["tool_calls_used"] = 4
    with pytest.raises(ValidationError):
        PedagogicalDecision.model_validate(raw)
