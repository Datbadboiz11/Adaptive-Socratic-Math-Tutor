"""Agent chạy trên nội dung đã duyệt của Member 2 (backend/app/agent/approved_content.py)."""
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agent.approved_content import (  # noqa: E402
    ApprovedTools, answer_forms, approved_services, load_approved_content,
)
from app.agent.decision import DecisionConfig  # noqa: E402
from app.agent.graph import TurnInput, TutorEngine  # noqa: E402

CONTENT = load_approved_content()
E06 = "D-E06-M2-ORIG02-P-01"   # 2x² − 7x + 3 = 0, họ 1
N02 = "D-N02-M2-ORIG02-P-01"   # (−13)·(−4)


def engine(configuration="rule_policy"):
    return TutorEngine(DecisionConfig(configuration=configuration, policy_version="rule-policy-0.1.0"),
                       approved_services(CONTENT))


def submit(e, sid, *steps):
    return e.turn(sid, TurnInput(request_id=uuid4(), trigger="submit", steps=list(steps)))


def test_problem_bank_is_the_approved_member2_release():
    assert len(CONTENT.problems) == 78
    assert len({p.ref.concept_id for p in CONTENT.problems.values()}) == 13
    assert all(p.validator_task["review"]["status"] == "human_approved"
               and p.validator_task["assessment_mode"] == "member2-final-answer-1.0.0" for p in CONTENT.problems.values())
    assert len(CONTENT.chunks) == 91


def test_public_problem_data_carries_no_answer():
    ref, prompt = CONTENT.problem_ref(E06), CONTENT.problem_prompt(E06)
    assert "reference_answer" not in ref.model_dump() and "25;{1/2,3}" not in prompt
    assert "reference_answer" not in CONTENT.validator_task(E06)  # validator tự tính đáp án từ đề


def test_rag_keeps_the_kb_rule_against_same_family_examples():
    family = CONTENT.problem_ref(E06).template_family_id
    skill = CONTENT.problem_ref(E06).target_skill_id
    retrieved = CONTENT.retrieve({skill}, E06, primary=skill)
    examples = [c for c in retrieved if c.content_type == "example"]
    assert examples and len(retrieved) <= 10
    blocked = {chunk.content.content_id for chunk in CONTENT.chunks
               if chunk.family_id == family or family in chunk.lineage_ids}
    assert blocked and not blocked & {c.content_id for c in retrieved}
    assert {c.content_type for c in retrieved} >= {"hint", "explanation"}


def test_explanations_use_the_highest_agent_disclosure_level():
    levels = {c.content.content_type: set() for c in CONTENT.chunks}
    for chunk in CONTENT.chunks:
        levels[chunk.content.content_type].add(chunk.content.disclosure_level)
    assert levels == {"explanation": {4}, "hint": {1, 2, 3}, "example": {3}}


@pytest.mark.parametrize("answer, forms", [
    ("52", ("52",)),
    ("6*(3*x+5)", ("6*(3*x+5)",)),
    ("25;{1/2,3}", ("25", "1/2", "3")),
    ("(3,-20)", ("3", "-20")),
    ("[-7,+inf)", ("-7",)),
    ("R\\{-10/3}", ("-10/3",)),
    ("45/126 < 49/126", ("45/126", "49/126")),
    ("x; quyển; positive_integer; 4*x+7=39", ("4*x+7=39",)),
])
def test_structured_answers_are_split_into_checkable_values(answer, forms):
    assert answer_forms(answer) == forms


def test_wrong_then_right_answer_on_an_approved_problem():
    e = engine()
    sid = e.start("approved-1", E06).session_id
    assert submit(e, sid, "9;{1}").action == "diagnose"
    reply = submit(e, sid, "25;{1/2,3}")
    state = e.state(sid)
    assert reply.action == "check_transfer"
    new = CONTENT.problem_ref(state.current.problem_id)
    assert new.concept_id == "E06" and new.template_family_id != CONTENT.problem_ref(E06).template_family_id


def test_copying_the_prompt_is_not_evidence_of_mastery():
    e = engine()
    sid = e.start("approved-2", N02).session_id
    reply = submit(e, sid, "(-13)*(-4)")
    state = e.state(sid)
    assert reply.action == "clarify" and state.current.problem_id == N02
    assert state.latest_assessment.assessment_status == "unverified"
    assert all(skill.independent_observations == 0 for skill in state.skills)


def test_final_answer_problems_follow_the_web_rule_and_create_no_bkt_evidence():
    """Web trả ``not_target_evidence`` cho 13 pack chấm đáp án cuối (``tutor.outcome_eligibility``) và không
    tạo observation. Agent làm giống hệt: giữ kết quả đúng và lịch sử làm bài, mastery không đổi."""
    from app import tutor

    from app.agent.decision import AssessmentView
    from app.agent.observation import ObservationLedger

    e = engine()
    sid = e.start("approved-3", N02).session_id
    opportunity = str(e.state(sid).current.opportunity_id)
    submit(e, sid, "52")
    state = e.state(sid)
    assert N02 in state.attempted_problem_ids
    ledger = ObservationLedger.model_validate(e.graph.get_state(e._cfg(sid)).values["observation_ledger"])
    assert opportunity in ledger.verified_attempts and opportunity not in ledger.observed
    observer = approved_services(CONTENT).observer
    fresh = e.state(e.start("approved-3b", N02).session_id)
    correct = AssessmentView(assessment_id=uuid4(), assessment_status="verified_correct",
                             primary_skill_id=fresh.current.target_skill_id)
    graded = fresh.model_copy(update={"latest_assessment": correct})
    status = observer(graded, None, ObservationLedger()).status
    assert (status.eligible, status.reason) == (False, "not_target_evidence")
    assert all(skill.independent_observations == 0 for skill in state.skills)
    web = tutor.outcome_eligibility(CONTENT.validator_task(N02), {}, {}, False, False)
    assert web == {"eligible": False, "reason": "not_target_evidence"}
    assert not any(CONTENT.counts_as_evidence(pid) for pid in CONTENT.problems)


@pytest.mark.parametrize("configuration, rag, kg", [("no_rag", False, True), ("no_kg", True, False)])
def test_ablation_switches_turn_off_rag_or_kg(configuration, rag, kg):
    e = engine()
    state = e.state(e.start(f"approved-{configuration}", E06).session_id)
    ctx = ApprovedTools(CONTENT)(state, DecisionConfig(configuration=configuration, policy_version="rule-policy-0.1.0"))
    assert bool(ctx.retrieved) is rag and ctx.kg_enabled is kg and ctx.rag_enabled is rag
    assert ctx.problems and all(p.problem_id in CONTENT.problems for p in ctx.problems)


def test_unfinished_work_gets_a_finish_your_answer_message_not_unreadable():
    from app.generation.templates import UNFINISHED_MESSAGE

    e = engine()
    sid = e.start("approved-4", N02).session_id
    reply = submit(e, sid, "(-13)*(-4)")
    assert e.state(sid).latest_assessment.unfinished
    assert reply.message == UNFINISHED_MESSAGE and "52" not in reply.message
    other = submit(e, sid, "abc ?")
    assert other.action == "clarify" and other.message != UNFINISHED_MESSAGE


# ---------------------------------------------------------------- verifier trên đáp án thật

def response_input(problem_id):
    from app.agent.decision import DecisionProposal
    from app.generation.contracts import ResponseInput

    return ResponseInput(decision=DecisionProposal.model_construct(action="minimal_hint", problem_id=None),
                         problem_id=problem_id, problem_prompt=CONTENT.problem_prompt(problem_id),
                         new_problem_prompt=None, content=(), assessment=None, submission=(), student_message=None)


@pytest.mark.parametrize("message", [
    "Biệt thức bằng 25 nên nghiệm là 1/2 và 3.",
    "Đáp số: x = 3.",
])
def test_verifier_blocks_a_message_that_states_the_answer(message):
    from app.generation.contracts import Check
    from app.generation.verifier import ResponseVerifier

    verifier = ResponseVerifier(CONTENT.answer_key)
    assert verifier.answer_check(response_input(E06), message) == Check.ANSWER_LEAK


@pytest.mark.parametrize("problem_id, leak", [
    ("D-F08-M2-ORIG02-P-06", "Đây không phải hàm số mũ. Em kiểm tra lại cơ số được không?"),
    ("D-E06-M2-ORIG02-P-02", "Hai nghiệm là (-1-sqrt(3))/2 và (-1+sqrt(3))/2."),
    ("D-N05-M2-ORIG02-P-01", "Phân số thứ nhất nhỏ hơn phân số thứ hai."),
    ("D-E06-M2-ORIG02-P-05", "Phương trình vô nghiệm. Em kiểm tra lại biệt thức được không?"),
    ("D-E06-M2-ORIG02-P-06", "Phương trình vô nghiệm. Em kiểm tra lại biệt thức được không?"),
    ("D-E03-M2-ORIG02-P-01", "Nhớ rằng x phải là số nguyên dương nhé."),
])
def test_answers_the_verifier_cannot_read_switch_off_llm_wording(problem_id, leak):
    """Câu lộ đáp án bằng chữ hoặc căn không bị verifier bắt, nên những bài này không có bộ đáp án:
    responder bỏ qua LLM (``answer_key_missing``) và chỉ dùng template, vốn không nêu đáp án."""
    from app.generation.responder import Responder
    from app.generation.templates import TemplateGenerator
    from app.generation.verifier import ResponseVerifier

    assert CONTENT.answer_key(problem_id) is None
    verifier = ResponseVerifier(CONTENT.answer_key)
    inp = response_input(problem_id)
    assert not verifier.has_keys(inp)
    responder = Responder(TemplateGenerator(), verifier, llm=object())
    assert responder._skip_reason(inp) == "answer_key_missing"


# ---------------------------------------------------------------- mức tiết lộ

def test_retrieval_never_exceeds_one_level_above_the_current_hint_level():
    e = engine()
    state = e.state(e.start("approved-levels", E06).session_id)
    assert state.support.hint_level == 0
    ctx = ApprovedTools(CONTENT)(state, DecisionConfig(configuration="full", policy_version="rule-policy-0.1.0"))
    assert ctx.retrieved and max(c.disclosure_level for c in ctx.retrieved) <= 1
    higher = state.model_copy(update={"support": state.support.model_copy(update={"hint_level": 3})})
    ctx = ApprovedTools(CONTENT)(higher, DecisionConfig(configuration="full", policy_version="rule-policy-0.1.0"))
    assert {c.content_type for c in ctx.retrieved} >= {"example", "explanation"}


def test_exported_contract_schemas_are_current():
    import subprocess

    result = subprocess.run([sys.executable, str(ROOT / "scripts/exports/export_agent_contracts.py"), "--check"],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_answer_key_covers_the_whole_answer():
    """Bài có bộ đáp án thì mọi phần của đáp án (trừ dấu ngăn, ngoặc, ``R`` và vô cực) phải nằm trong
    bộ đó; nếu còn phần chữ hoặc tập rỗng mà verifier không đọc được thì bài phải dùng phản hồi mẫu."""
    import re

    for problem_id, problem in CONTENT.problems.items():
        key = CONTENT.answer_key(problem_id)
        if key is None:
            continue
        rest = problem.reference_answer
        for form in sorted(key.final_answers, key=len, reverse=True):  # "-1" trước "1"
            rest = rest.replace(form, "")
        rest = re.sub(r"[+-]?inf", "", rest)
        rest = re.sub(r"[\s;,{}|()\[\]<>]", "", rest).replace("\\", "").replace("R", "")
        assert not rest and not re.search(r"\{\s*\}", problem.reference_answer), (problem_id, rest)
