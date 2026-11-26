"""Observation + BKT của Member 1 (app.knowledge) trong graph: app.agent.observation."""
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import knowledge  # noqa: E402
from app.agent.decide import ProposalOutcome  # noqa: E402
from app.agent.decision import (  # noqa: E402
    AssessmentView, DecisionConfig, DecisionProposal, DecisionSource, EvidenceKind, EvidenceRef, SupportState,
)
from app.agent.graph import Services, TurnInput, TutorEngine  # noqa: E402
from app.agent.observation import (  # noqa: E402
    KnowledgeObserver, LegacyCheckpoint, ObservationLedger, ParameterVersionMismatch, bootstrap_parameters,
    observe_submission,
)

E02 = "SK-E02-SOLVE"
EMPTY = ObservationLedger()


def fresh_state(relation="initial", status="verified_correct", skill=E02):
    engine = TutorEngine(DecisionConfig(configuration="rule_policy", policy_version="rule-policy-0.1.0"))
    s = engine.state(engine.start("obs", "E02-P001").session_id)
    return submitted(s.model_copy(update={"current": s.current.model_copy(update={"relation": relation})}),
                     status, skill)


def submitted(s, status="verified_correct", skill=E02):
    a = AssessmentView(assessment_id=uuid4(), assessment_status=status, primary_skill_id=skill)
    return s.model_copy(update={"latest_assessment": a})


def test_first_independent_correct_updates_bkt_with_member1_formula():
    s = fresh_state()
    result, trace = observe_submission(s, EMPTY)
    p = knowledge.PARAMETERS
    expected = knowledge.update(p["prior"], True, p)
    (skill,) = result.skills
    assert result.status.eligible and result.status.reason == "first_independent_verified"
    assert skill.p_mastery == pytest.approx(expected["mastery_after"])
    assert skill.parameter_version == knowledge.VERSION
    assert trace.prediction_before == pytest.approx(expected["prediction_before"])
    assert str(s.current.opportunity_id) in result.ledger.observed


# ---------------------------------------------------------------- bài cùng họ mẫu (review P2 #1)

def test_same_family_after_independent_work_is_still_evidence():
    result, _ = observe_submission(fresh_state("near_practice"), EMPTY)
    assert result.status.reason == "first_independent_verified"


def test_same_family_after_help_on_another_problem_is_not_evidence():
    s = fresh_state("near_practice")
    ledger = ObservationLedger(assisted={str(uuid4()): s.current.template_family_id})
    result, _ = observe_submission(s, ledger)
    assert result.status.reason == "near_practice" and result.skills == []


def test_help_in_another_family_does_not_block():
    ledger = ObservationLedger(assisted={str(uuid4()): "some_other_family"})
    assert observe_submission(fresh_state("near_practice"), ledger)[0].status.eligible


def test_ledger_records_help_for_the_problem_the_decision_acts_on():
    s = fresh_state()
    assert s.support == SupportState()
    neutral = DecisionProposal.model_construct(action="next_problem")
    assert EMPTY.note_decision(s, neutral) == EMPTY  # không trợ giúp: không ghi
    hint = DecisionProposal.model_construct(action="minimal_hint")
    expected = {str(s.current.opportunity_id): s.current.template_family_id}
    assert EMPTY.note_decision(s, hint).assisted == expected
    hinted = s.model_copy(update={"support": SupportState(hint_level=1)})
    assert EMPTY.note_decision(hinted, neutral).assisted == expected  # trợ giúp từ lượt trước


class BacktrackAtOnce:
    """Agent chọn backtrack ngay sau lần sai đầu tiên (review: ca tái hiện qua LangGraph)."""

    def __call__(self, state, ctx):
        proposal = DecisionProposal(
            action="backtrack", intent="review_prerequisite", target_skill_id="SK-A02-DISTRIBUTE",
            evidence=[EvidenceRef(kind=EvidenceKind.ASSESSMENT, id=str(state.latest_assessment.assessment_id))],
            edge_ids=["PRE-A02-E02"], problem_id="A02-P001", reason="Lỗi phân phối, ôn A02.")
        return ProposalOutcome(proposal, DecisionSource.AGENT)


def test_backtrack_keeps_the_help_given_on_the_parent_problem():
    engine = TutorEngine(DecisionConfig(configuration="full", policy_version="rule-policy-0.1.0"),
                         Services(proposer=BacktrackAtOnce()))
    sid = engine.start("obs", "E02-P001").session_id
    parent = engine.state(sid).current
    reply = engine.turn(sid, TurnInput(request_id=uuid4(), trigger="submit", steps=["2x - 3 = 10", "2x = 13"]))
    assert reply.action == "backtrack" and engine.state(sid).current.problem_id == "A02-P001"
    ledger = ObservationLedger.model_validate(engine.graph.get_state(engine._cfg(sid)).values["observation_ledger"])
    assert ledger.assisted == {str(parent.opportunity_id): parent.template_family_id}


def test_checkpoint_from_before_the_ledger_is_refused_not_read_as_empty():
    """Checkpoint của bản trước chỉ có ``observed_opportunities``: báo rõ, không đọc như sổ trống."""
    engine = TutorEngine(DecisionConfig(configuration="rule_policy", policy_version="rule-policy-0.1.0"))
    new = engine.graph.get_state(engine._cfg(engine.start("obs", "E02-P001").session_id)).values
    old_sid = uuid4()
    legacy = {key: value for key, value in new.items() if key != "observation_ledger"}
    legacy["student"] = {**legacy["student"], "session_id": str(old_sid)}
    engine.graph.update_state(engine._cfg(old_sid), {**legacy, "observed_opportunities": []}, as_node="commit")
    with pytest.raises(LegacyCheckpoint):
        engine.turn(old_sid, TurnInput(request_id=uuid4(), trigger="submit", steps=["x = 8"]))


def test_returning_to_the_parent_problem_is_not_evidence():
    result, _ = observe_submission(fresh_state("repeat"), EMPTY)
    assert result.status.reason == "repeat"


# ---------------------------------------------------------------- lần thử đầu tiên (review P2 #2)

def test_second_verified_submission_on_the_same_problem_is_not_a_first_attempt():
    """Lần một sai ở skill khác (not_target_evidence), lần hai đúng: không còn là lần thử đầu."""
    s = fresh_state(status="verified_incorrect", skill="SK-A02-DISTRIBUTE")
    first, _ = observe_submission(s, EMPTY)
    assert first.status.reason == "not_target_evidence"
    second, _ = observe_submission(submitted(s), first.ledger)
    assert second.status.reason == "repeat" and second.skills == []


@pytest.mark.parametrize("status", ["needs_clarification", "unverified"])
def test_unreadable_or_unverified_submission_still_allows_a_first_attempt(status):
    s = fresh_state(status=status, skill=None)
    first, _ = observe_submission(s, EMPTY)
    assert first.status.reason == "not_verified" and first.skills == []
    second, _ = observe_submission(submitted(s), first.ledger)
    assert second.status.reason == "first_independent_verified"


def test_graph_counts_only_the_first_verified_submission():
    engine = TutorEngine(DecisionConfig(configuration="rule_policy", policy_version="rule-policy-0.1.0"))
    sid = engine.start("obs", "E02-P001").session_id
    engine.turn(sid, TurnInput(request_id=uuid4(), trigger="submit", steps=["2x - 3 = 10", "2x = 13"]))
    assert engine.state(sid).observation.reason == "not_target_evidence"
    # Lần nộp thứ hai trên cùng bài (sau một lượt chẩn đoán) không tạo observation. Quyết định sau đó
    # chuyển bài nên state không còn giữ observation của lượt; kiểm tra qua mastery.
    engine.turn(sid, TurnInput(request_id=uuid4(), trigger="submit", steps=["2x - 6 = 10", "2x = 16", "x = 8"]))
    state = engine.state(sid)
    assert state.current.problem_id != "E02-P001"
    assert all(s.independent_observations == 0 for s in state.skills)


# ---------------------------------------------------------------- phiên bản tham số (review P2 #3)

def test_mastery_from_another_parameter_version_is_not_updated_silently():
    s = fresh_state()
    first, _ = observe_submission(s, EMPTY)
    nxt = submitted(s.model_copy(update={
        "skills": first.skills, "current": s.current.model_copy(update={"opportunity_id": uuid4()})}))
    fitted = dict(bootstrap_parameters(E02), parameter_version="fitted-2.0.0")
    with pytest.raises(ParameterVersionMismatch):
        observe_submission(nxt, first.ledger, lambda skill_id: fitted)
    assert observe_submission(nxt, first.ledger)[0].status.eligible  # cùng phiên bản thì vẫn chạy


def test_per_skill_parameters_can_be_injected():
    custom = dict(bootstrap_parameters(E02), prior=0.5, parameter_version="custom-1")
    result = KnowledgeObserver(lambda skill_id: custom)(fresh_state(), None, EMPTY)
    (skill,) = result.skills
    assert skill.parameter_version == "custom-1"
    assert skill.p_mastery == pytest.approx(knowledge.update(0.5, True, custom)["mastery_after"])


def test_graph_uses_member1_observer_by_default():
    assert isinstance(Services().observer, KnowledgeObserver)
