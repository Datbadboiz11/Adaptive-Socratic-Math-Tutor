"""Policy gate, Rule-policy v1 và chuỗi fallback trên bộ tình huống dev."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent import decide as decide_module  # noqa: E402
from app.agent.decide import ProposalOutcome, resolve_decision  # noqa: E402
from app.agent.decision import (  # noqa: E402
    DecisionConfig, DecisionProposal, DecisionSource, PedagogicalAction, SkillState, StudentState,
)
from app.agent.gate import gate_violations, policy_gate  # noqa: E402
from app.agent.rule_policy import compute_readiness, estimate, last_resort, rule_policy  # noqa: E402
from research.agent.scenarios import merge  # noqa: E402
from app.agent.tools import TurnContext  # noqa: E402

FIXTURES = json.loads((ROOT / "contracts/agent/fixtures.v1.json").read_text(encoding="utf-8"))
SCENARIOS = json.loads((ROOT / "contracts/agent/scenarios.dev.v1.json").read_text(encoding="utf-8"))
ASSESSMENT = "55555555-5555-4555-8555-555555555555"


def scenario(sid):
    sc = next(s for s in SCENARIOS["scenarios"] if s["id"] == sid)
    state = StudentState.model_validate(merge(FIXTURES["student_state"], sc.get("state_patch", {})))
    ctx = TurnContext.model_validate(merge(SCENARIOS["base_context"], sc.get("context_patch", {})))
    return sc, state, ctx


def base():
    return scenario("SC-01")[1:]


def proposal(**fields):
    data = {"action": "minimal_hint", "intent": "locate_error", "target_skill_id": "SK-A02-DISTRIBUTE",
            "hint_level": 1, "evidence": [{"kind": "assessment", "id": ASSESSMENT}], "reason": "Thử."}
    data.update(fields)
    return DecisionProposal.model_validate(data)


CONFIG = DecisionConfig(configuration="rule_policy", policy_version="rule-policy-0.1.0")
NOW = datetime(2026, 11, 13, 10, tzinfo=timezone.utc)


# ---------------------------------------------------------------- Rule-policy trên bộ tình huống

@pytest.mark.parametrize("sid", [s["id"] for s in SCENARIOS["scenarios"]])
def test_rule_policy_scenarios(sid):
    sc, state, ctx = scenario(sid)
    p = rule_policy(state, ctx)
    assert (p.action, p.intent) == (sc["expected_rule_action"], sc["expected_rule_intent"])
    assert p.action in sc["acceptable_actions"]
    assert p.action not in sc["forbidden_actions"]
    gate = policy_gate(state, p, ctx)
    assert gate.status == "accepted", gate.violated_rules


def test_scenarios_cover_every_action():
    actions = {s["expected_rule_action"] for s in SCENARIOS["scenarios"]}
    assert actions == {a.value for a in PedagogicalAction}


def test_scenario_labels_are_consistent():
    for sc in SCENARIOS["scenarios"]:
        assert not set(sc["acceptable_actions"]) & set(sc["forbidden_actions"]), sc["id"]
    assert SCENARIOS["split"] == "dev"


# ---------------------------------------------------------------- Từng luật gate

def violations(state, ctx, **fields):
    return gate_violations(state, proposal(**fields), ctx)


def has(codes, prefix):
    return any(c.startswith(prefix) for c in codes)


def test_g01_unclear_input_only_clarify():
    _, state, ctx = scenario("SC-05")
    assert has(violations(state, ctx, evidence=[{"kind": "assessment", "id": ASSESSMENT}]), "G01")


def test_g02_hint_cannot_jump():
    state, ctx = base()
    assert has(violations(state, ctx, hint_level=2), "G02")
    assert not has(violations(state, ctx, hint_level=1), "G02")


def test_g03_unknown_evidence():
    state, ctx = base()
    assert has(violations(state, ctx, evidence=[{"kind": "assessment", "id": "not-in-state"}]), "G03")


def test_g04_content_must_be_retrieved_and_within_disclosure():
    state, ctx = base()
    assert has(violations(state, ctx, content_ids=["KB-UNKNOWN"]), "G04_content_not_retrieved")
    assert has(violations(state, ctx, content_ids=["KB-A02-EXPLAIN-01"]), "G04_disclosure_above")


def test_g05_edges_must_be_returned_and_link_target():
    state, ctx = base()
    common = dict(action="backtrack", intent="review_prerequisite", hint_level=0, problem_id="A02-P001")
    assert has(violations(state, ctx, edge_ids=["PRE-FAKE"], **common), "G05_edge_not_returned")
    assert has(violations(state, ctx, edge_ids=["PRE-N01-A02"], **common), "G05_edge_does_not_link")
    assert not has(violations(state, ctx, edge_ids=["PRE-A02-E02"], **common), "G05")


def test_g06_g07_new_error_and_readiness_block_advance():
    state, ctx = base()
    codes = violations(state, ctx, action="next_problem", intent="advance_concept", hint_level=0,
                       target_skill_id="SK-E03-PRIMARY", problem_id="E03-P001")
    assert has(codes, "G06") and has(codes, "G07")


def test_g08_backtrack_depth_loop_and_correct():
    _, state, ctx = scenario("SC-11")
    p = dict(action="backtrack", intent="review_prerequisite", hint_level=0, edge_ids=["PRE-N01-A02"],
             target_skill_id="SK-N01-SIGNED-ADD", problem_id="A02-P002",
             evidence=[{"kind": "assessment", "id": ASSESSMENT}])
    assert has(gate_violations(state, proposal(**p), ctx), "G08_no_backtrack_when_correct")
    deep = state.model_copy(update={"return_stack": state.return_stack * 2})
    assert has(gate_violations(deep, proposal(**p), ctx), "G08_backtrack_depth")
    # Đã ghé A02 trong nhánh hiện tại (đang ở return stack) thì không backtrack lại A02.
    _, state, ctx = scenario("SC-08")
    frame = {"problem_id": "A02-P001", "opportunity_id": str(uuid4()), "concept_id": "A02",
             "skill_id": "SK-A02-DISTRIBUTE", "hint_level": 0}
    loop = StudentState.model_validate(merge(state.model_dump(mode="json"), {"return_stack": [frame]}))
    codes = gate_violations(loop, proposal(action="backtrack", intent="review_prerequisite", hint_level=0,
                                           edge_ids=["PRE-A02-E02"], problem_id="A02-P002"), ctx)
    assert has(codes, "G08_backtrack_loop")


def test_g09_return_must_match_stack():
    _, state, ctx = scenario("SC-11")
    codes = violations(state, ctx, action="next_problem", intent="return_to_parent", hint_level=0,
                       target_skill_id="SK-E02-SOLVE", problem_id="E02-P002")
    assert has(codes, "G09")


def test_g10_stuck_limit_and_switch():
    _, state, ctx = scenario("SC-14")
    assert has(violations(state, ctx), "G10_stuck_limit")
    state, ctx = base()
    codes = violations(state, ctx, action="next_problem", intent="switch_problem", hint_level=0,
                       target_skill_id="SK-E02-SOLVE", problem_id="E02-P002")
    assert has(codes, "G10_switch_requires_stuck")


def test_g11_high_level_needs_new_approach():
    _, state, ctx = scenario("SC-08")
    assert has(violations(state, ctx, hint_level=2), "G11")


def test_g12_g13_problem_rules():
    _, state, ctx = scenario("SC-10")
    same_family = dict(action="check_transfer", intent="independent_check", hint_level=0,
                       target_skill_id="SK-E02-SOLVE")
    assert has(violations(state, ctx, problem_id="E02-P002", **same_family), "G12")
    assert has(violations(state, ctx, problem_id="E02-P999", **same_family), "G13_problem_not_in_bank")
    assert has(violations(state, ctx, problem_id="E02-P001", **same_family), "G13_same_problem")
    assert has(violations(state, ctx, problem_id="A02-P002", **same_family), "G13_problem_skill_mismatch")


def test_g14_pause_must_end():
    _, state, ctx = scenario("SC-13")
    assert has(violations(state, ctx), "G14")


def test_g16_transfer_requires_correct():
    state, ctx = base()
    codes = violations(state, ctx, action="check_transfer", intent="independent_check", hint_level=0,
                       target_skill_id="SK-E02-SOLVE", problem_id="E02-P003")
    assert has(codes, "G16") and has(codes, "G06")


def test_g17_conceptual_question_needs_active_hypothesis():
    state, ctx = base()
    codes = violations(state, ctx, action="conceptual_question", intent="target_misconception", hint_level=0)
    assert has(codes, "G17")
    ok = violations(state, ctx, action="conceptual_question", intent="target_misconception", hint_level=0,
                    evidence=[{"kind": "assessment", "id": ASSESSMENT}, {"kind": "hypothesis", "id": "HYP-001"}])
    assert not ok


# ---------------------------------------------------------------- Knowledge Graph (PRD FR-08)

NO_EVIDENCE = {"latest_assessment": {"primary_skill_id": "SK-E02-SOLVE", "error_family": "transformation_error",
                                     "misconception_candidate": None, "diagnosis_status": "unknown"},
               "hypotheses": [], "skills": []}
STUCK_AT_3 = {"support": {"hint_level": 3, "support_turns_on_node": 3, "no_progress_turns": 3}}


def patched(patch):
    state, ctx = base()
    return StudentState.model_validate(merge(state.model_dump(mode="json"), patch)), ctx


def probe(skill, status="pending"):
    return {"decision_id": str(uuid4()), "skill_id": skill, "status": status,
            "answer_turn_id": None if status == "pending" else str(uuid4())}


def test_g05_two_level_probe_needs_the_whole_chain():
    state, ctx = base()
    probe = dict(action="diagnose", intent="probe_prerequisite", hint_level=0, target_skill_id="SK-N01-SIGNED-ADD")
    assert has(violations(state, ctx, edge_ids=["PRE-N01-A02"], **probe), "G05_edge_does_not_link")
    assert not violations(state, ctx, edge_ids=["PRE-A02-E02", "PRE-N01-A02"], **probe)
    # Cạnh thừa không nằm trên đường đi tới concept đang học cũng bị từ chối.
    assert has(violations(state, ctx, edge_ids=["PRE-A02-E02", "PRE-N01-A02", "PRE-A01-A03"], **probe), "G05")


def test_g08_backtrack_moves_one_level_per_step():
    state, ctx = base()
    codes = violations(state, ctx, action="backtrack", intent="review_prerequisite", hint_level=0,
                       target_skill_id="SK-N01-SIGNED-ADD", edge_ids=["PRE-A02-E02", "PRE-N01-A02"],
                       problem_id="N01-P001")
    assert has(codes, "G08_backtrack_one_level_per_step")


def test_g18_backtrack_requires_evidence_about_that_prerequisite():
    state, ctx = patched(NO_EVIDENCE)
    back = dict(action="backtrack", intent="review_prerequisite", hint_level=0, edge_ids=["PRE-A02-E02"],
                problem_id="A02-P001")
    assert has(violations(state, ctx, **back), "G18")  # A02 chỉ là ứng viên trên graph
    # Review P1: đã hỏi kiểm tra chưa phải bằng chứng; cần câu trả lời được xác minh là chưa đạt.
    for status in ("pending", "unverified", "demonstrated"):
        asked, _ = patched({**NO_EVIDENCE, "probes": [probe("SK-A02-DISTRIBUTE", status)]})
        assert has(violations(asked, ctx, **back), "G18"), status
    failed, _ = patched({**NO_EVIDENCE, "probes": [probe("SK-A02-DISTRIBUTE", "not_demonstrated")]})
    assert not has(violations(failed, ctx, **back), "G18")
    state, ctx = base()  # lỗi vừa chấm được quy cho chính skill A02
    assert not violations(state, ctx, **back)


def test_rule_policy_probes_before_backtracking_to_unproven_prerequisite():
    state, ctx = patched({**NO_EVIDENCE, **STUCK_AT_3})
    first = rule_policy(state, ctx)
    assert (first.action, first.intent) == ("diagnose", "probe_prerequisite")
    assert first.edge_ids == ["PRE-A02-E02"] and policy_gate(state, first, ctx).status == "accepted"
    # Đã hỏi nhưng chưa có câu trả lời được xác minh: không backtrack và không hỏi lại câu đó.
    for status in ("pending", "unverified"):
        waiting, _ = patched({**NO_EVIDENCE, **STUCK_AT_3, "trigger": "request_hint",
                              "probes": [probe(first.target_skill_id, status)]})
        p = rule_policy(waiting, ctx)
        assert p.action != "backtrack" and p.intent != "probe_prerequisite", status
        assert policy_gate(waiting, p, ctx).status == "accepted"
    failed, _ = patched({**NO_EVIDENCE, **STUCK_AT_3, "probes": [probe(first.target_skill_id, "not_demonstrated")]})
    second = rule_policy(failed, ctx)
    assert second.action == "backtrack" and second.problem_id == "A02-P001" and "probe_failed" in second.reason
    assert policy_gate(failed, second, ctx).status == "accepted"


def test_probe_state_rules():
    with pytest.raises(ValueError):  # câu đã đóng phải gắn với lượt trả lời
        patched({"probes": [{**probe("SK-A02-DISTRIBUTE", "not_demonstrated"), "answer_turn_id": None}]})
    with pytest.raises(ValueError):  # mỗi lúc chỉ chờ một câu
        patched({"probes": [probe("SK-A02-DISTRIBUTE"), probe("SK-A03-COLLECT")]})


def test_rule_policy_skips_prerequisite_the_student_already_masters():
    good = {"skill_id": "SK-A02-DISTRIBUTE", "p_mastery": 0.9, "independent_observations": 4,
            "recent_independent": [True, True, True, True], "parameter_version": "bkt-default-0.1.0"}
    state, ctx = patched({**NO_EVIDENCE, **STUCK_AT_3, "skills": [good]})
    p = rule_policy(state, ctx)
    # Không hỏi kiểm tra hay ôn A02 nữa; context không có ví dụ cho skill giải nên hỏi lại cách nghĩ.
    assert p.intent == "elicit_reasoning" and not p.edge_ids


READY = {"latest_assessment": {"assessment_status": "verified_correct", "first_error_step": None,
                               "primary_skill_id": "SK-E02-SOLVE", "error_family": None,
                               "misconception_candidate": None, "diagnosis_status": "unknown"},
         "hypotheses": [], "readiness": {"ready_to_advance": True, "criteria_version": "stop-0.1.0", "unmet": []}}


def test_next_concept_cites_its_edge_and_avoids_weak_other_prerequisite():
    state, ctx = patched(READY)
    p = rule_policy(state, ctx)
    assert (p.intent, p.problem_id, p.edge_ids) == ("advance_concept", "E03-P001", ["PRE-E02-E03"])
    assert policy_gate(state, p, ctx).status == "accepted"
    wrong = p.model_copy(update={"edge_ids": ["PRE-E02-E04"]})  # cạnh tới E04 nhưng bài thuộc E03
    assert has(gate_violations(state, wrong, ctx), "G05_edge_does_not_link")
    assert has(gate_violations(state, p.model_copy(update={"edge_ids": ["PRE-A02-E02"]}), ctx), "G05_edge_not_returned")
    # E03 còn cần A01; A01 đang yếu thì chưa chuyển sang E03 mà tăng độ khó trong E02.
    weak = {"skill_id": "SK-A01-EVALUATE", "p_mastery": 0.2, "independent_observations": 3,
            "recent_independent": [False, False, True], "parameter_version": "bkt-default-0.1.0"}
    state, ctx = patched({**READY, "skills": [weak]})
    assert rule_policy(state, ctx).intent == "advance_difficulty"


def test_g19_advance_concept_must_follow_a_kg_edge():
    state, ctx = patched(READY)
    advance = dict(action="next_problem", intent="advance_concept", hint_level=0)
    e03 = dict(target_skill_id="SK-E03-PRIMARY", problem_id="E03-P001")
    a02 = dict(target_skill_id="SK-A02-DISTRIBUTE", problem_id="A02-P001")
    # Review P1: bỏ edge_ids từng đủ để vượt mọi kiểm tra chuyển concept.
    assert has(violations(state, ctx, **advance, **e03), "G19_advance_concept_requires_edge")
    assert has(violations(state, ctx, **advance, **a02), "G19_advance_concept_requires_edge")
    assert not violations(state, ctx, edge_ids=["PRE-E02-E03"], **advance, **e03)
    # Không có KG (No-KG hoặc tool lỗi) thì không chuyển concept, kể cả khi có trích cạnh.
    no_kg = ctx.model_copy(update={"edges": [], "next_concepts": [], "kg_enabled": False})
    assert has(violations(state, no_kg, **advance, **a02), "G19_advance_concept_requires_kg")
    assert has(violations(state, no_kg, edge_ids=["PRE-E02-E03"], **advance, **e03), "G19_advance_concept_requires_kg")


def test_scenario_edges_exist_in_registry():
    from app.kg.graph import KnowledgeGraph

    graph = {e.edge_id: (e.source_concept_id, e.target_concept_id) for e in KnowledgeGraph.load().edges}
    contexts = [SCENARIOS["base_context"]] + [s.get("context_patch", {}) for s in SCENARIOS["scenarios"]]
    for context in contexts:
        for item in context.get("edges", []):
            assert graph.get(item["edge_id"]) == (item["source_concept_id"], item["target_concept_id"])
        for item in context.get("next_concepts", []):
            assert graph.get(item["edge_id"], (None, None))[1] == item["concept_id"]


def test_decision_log_keeps_kg_candidates():
    state, ctx = patched(STUCK_AT_3)
    record = resolve_decision(state, ctx, ProposalOutcome(rule_policy(state, ctx), DecisionSource.RULE_POLICY),
                              CONFIG, decision_id=uuid4(), created_at=NOW)
    assert record.final.action == "backtrack" and record.final.edge_ids == ["PRE-A02-E02"]
    assert set(record.final.edge_ids) < set(record.candidate_edge_ids) and len(record.candidate_edge_ids) == 9


# ---------------------------------------------------------------- Chuỗi fallback

def test_agent_proposal_accepted():
    state, ctx = base()
    good = rule_policy(state, ctx)
    record = resolve_decision(state, ctx, ProposalOutcome(good, DecisionSource.AGENT),
                              CONFIG.model_copy(update={"configuration": "full"}),
                              decision_id=uuid4(), created_at=NOW)
    assert record.final_source == DecisionSource.AGENT and record.final == good


def test_agent_rejected_falls_back_to_rule_policy():
    state, ctx = base()
    bad = proposal(action="next_problem", intent="advance_concept", hint_level=0, target_skill_id="SK-E03-PRIMARY",
                   problem_id="E03-P001")
    record = resolve_decision(state, ctx, ProposalOutcome(bad, DecisionSource.AGENT),
                              CONFIG.model_copy(update={"configuration": "full"}),
                              decision_id=uuid4(), created_at=NOW)
    assert record.fallback_reason == "gate_rejected"
    assert record.final == rule_policy(state, ctx)
    assert record.fallback_gate.status == "accepted"


def test_agent_timeout_falls_back():
    state, ctx = base()
    record = resolve_decision(state, ctx, ProposalOutcome(None, DecisionSource.AGENT, "agent_timeout"),
                              CONFIG.model_copy(update={"configuration": "full"}),
                              decision_id=uuid4(), created_at=NOW)
    assert record.fallback_reason == "agent_timeout" and record.gate is None


def test_last_resort_when_rule_policy_invalid(monkeypatch):
    state, ctx = base()
    invalid = proposal(hint_level=2)  # G02
    monkeypatch.setattr(decide_module, "rule_policy", lambda s, c: invalid)
    record = resolve_decision(state, ctx, ProposalOutcome(invalid, DecisionSource.RULE_POLICY), CONFIG,
                              decision_id=uuid4(), created_at=NOW)
    assert record.final == last_resort(state)
    assert record.final.intent == "system_fallback"


# ---------------------------------------------------------------- Ước lượng và readiness

def test_estimate_depends_on_mastery_view():
    skill = SkillState(skill_id="SK-X", p_mastery=0.9, independent_observations=4,
                       recent_independent=[True, False, True, True])
    assert estimate(skill, "bkt") == (0.9, 4)
    assert estimate(skill, "recent_ratio") == (0.75, 4)
    assert estimate(skill, "none") == (None, 4)


def hide_mastery(state, view):
    return state.model_copy(update={"mastery_view": view,
                                    "skills": [k.model_copy(update={"p_mastery": None}) for k in state.skills]})


@pytest.mark.parametrize("sid,heuristic,no_bkt", [
    ("SC-04", "prompt_self_check", "elicit_reasoning"),     # cần lịch sử tốt để coi là lỗi thao tác
    ("SC-15", "probe_prerequisite", "elicit_reasoning"),    # cần ước lượng skill nền thấp
])
def test_no_bkt_and_heuristic_decide_differently(sid, heuristic, no_bkt):
    # Review: hai cấu hình từng cho cùng state và cùng quyết định, nên ablation không phân biệt được.
    _, state, ctx = scenario(sid)
    for view, expected in (("recent_ratio", heuristic), ("none", no_bkt)):
        projected = hide_mastery(state, view)
        p = rule_policy(projected, ctx)
        assert p.intent == expected, view
        assert policy_gate(projected, p, ctx).status == "accepted"


def test_no_bkt_readiness_uses_evidence_log_only():
    _, state, _ = scenario("SC-12")
    evidence = state.model_copy(update={"hypotheses": [], "skills": [SkillState(
        skill_id="SK-E02-SOLVE", p_mastery=None, independent_observations=3,
        recent_independent=[False, True, True])]})
    assert compute_readiness(hide_mastery(evidence, "none")).ready_to_advance is True
    heuristic = compute_readiness(hide_mastery(evidence, "recent_ratio"))
    assert heuristic.unmet == ["estimate_below_threshold"]  # tỷ lệ 2/3 < 0.8


def test_readiness_rules():
    _, state, _ = scenario("SC-12")
    assert compute_readiness(state).ready_to_advance is False  # mới 4 obs nhưng p=0.61
    ready = state.model_copy(update={"skills": [SkillState(
        skill_id="SK-E02-SOLVE", p_mastery=0.9, independent_observations=4,
        recent_independent=[False, True, True, True])]})
    assert compute_readiness(ready).ready_to_advance is True
    blocked = StudentState.model_validate(merge(ready.model_dump(mode="json"), {"hypotheses": [
        {"hypothesis_id": "H", "misconception_id": "M", "skill_id": "SK-E02-SOLVE", "status": "suspected",
         "evidence_ids": ["x"]}]}))
    assert "unresolved_hypothesis" in compute_readiness(blocked).unmet


# ---------------------------------------------------------------- Phạm vi bài mới (G20) và giới hạn kẹt (G10)

def _new_problem(state, action, intent, skill, problem_id):
    return DecisionProposal.model_validate({
        "action": action, "intent": intent, "target_skill_id": skill, "problem_id": problem_id,
        "evidence": [{"kind": "assessment", "id": str(state.latest_assessment.assessment_id)}], "reason": "Thử."})


@pytest.mark.parametrize("action, intent", [("check_transfer", "independent_check"),
                                            ("next_problem", "continue_practice"),
                                            ("next_problem", "switch_problem")])
def test_g20_same_scope_problems_cannot_change_skill(action, intent):
    # Review: đang học E02 mà "kiểm tra chuyển giao" hay "luyện tiếp" sang A02 vẫn được chấp nhận.
    _, state, ctx = scenario("SC-10")
    p = _new_problem(state, action, intent, "SK-A02-DISTRIBUTE", "A02-P002")
    assert "G20_problem_outside_current_scope" in gate_violations(state, p, ctx)
    no_kg = ctx.model_copy(update={"kg_enabled": False, "edges": [], "next_concepts": []})
    assert "G20_problem_outside_current_scope" in gate_violations(state, p, no_kg)


def test_g20_check_transfer_on_current_skill_is_accepted():
    _, state, ctx = scenario("SC-10")
    p = _new_problem(state, "check_transfer", "independent_check", "SK-E02-SOLVE", "E02-P003")
    assert policy_gate(state, p, ctx).status == "accepted"


def test_g20_advance_difficulty_must_be_harder():
    _, state, ctx = scenario("SC-12")
    ready = state.model_copy(update={"current": state.current.model_copy(update={"difficulty": 1})})
    same = _new_problem(ready, "next_problem", "advance_difficulty", "SK-E02-SOLVE", "E02-P002")  # độ khó 1
    assert "G20_difficulty_not_higher" in gate_violations(ready, same, ctx)
    harder = _new_problem(ready, "next_problem", "advance_difficulty", "SK-E02-SOLVE", "E02-P003")  # độ khó 2
    assert not has(gate_violations(ready, harder, ctx), "G20")
    unknown = ready.model_copy(update={"current": ready.current.model_copy(update={"difficulty": None})})
    no_bank = ctx.model_copy(update={"problems": [q for q in ctx.problems if q.problem_id != "E02-P001"]})
    assert "G20_current_difficulty_unknown" in gate_violations(unknown, harder, no_bank)


def test_solved_after_support_limit_returns_to_parent():
    # Review: làm đúng bài nền sau 6 lượt hỗ trợ thì phải quay lại bài gốc, không bị đổi bài.
    _, state, ctx = scenario("SC-11")
    solved = state.model_copy(update={"support": state.support.model_copy(update={"support_turns_on_node": 6})})
    p = rule_policy(solved, ctx)
    assert (p.intent, p.problem_id) == ("return_to_parent", "E02-P001")
    assert policy_gate(solved, p, ctx).status == "accepted"


def test_support_limit_still_applies_while_unsolved():
    _, state, ctx = scenario("SC-14")
    assert rule_policy(state, ctx).intent == "switch_problem"
    assert has(violations(state, ctx), "G10_stuck_limit")
