"""Socratic LLM baseline (plan §18.1): chỉ nhận đề và hội thoại, cùng kiểm tra chống lộ lời giải với hệ thống."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.stubs import problem_prompt  # noqa: E402
from app.generation.contracts import Check  # noqa: E402
from app.generation.templates import SYSTEM_MESSAGE  # noqa: E402
from app.generation.verifier import ResponseVerifier  # noqa: E402
from app.llm.client import LLMCall, LLMCallFailed  # noqa: E402
from app.llm.fakes import FakeLLMClient  # noqa: E402
from research.agent.scenarios import load_scenarios  # noqa: E402
from research.evaluation.run_ablation import (  # noqa: E402
    SOCRATIC_LLM, VERIFIER, EchoBaseline, Models, run_ablation, run_turn, summarize, system_outputs,
)
from research.evaluation.socratic_baseline import (  # noqa: E402
    PROMPT_VERSION, BaselineTurn, SocraticLLMBaseline, build_input,
)

SCENARIOS = {sc.id: sc for sc in load_scenarios()}
LEAK = "Nghiệm của phương trình là x = 8 nhé."
GOOD = "Ở bước 1, em đã nhân 2 vào những số hạng nào trong ngoặc?"


def turn(scenario_id: str) -> BaselineTurn:
    return BaselineTurn.from_state(SCENARIOS[scenario_id].state, problem_prompt)


def baseline(*messages, verifier: ResponseVerifier = VERIFIER) -> SocraticLLMBaseline:
    client = FakeLLMClient([{"message": m} if isinstance(m, str) else m for m in messages])
    return SocraticLLMBaseline(client, verifier)


# --------------------------------------------------------------------------- model thấy gì

def test_the_model_sees_only_the_problem_and_the_conversation():
    """Không có kết quả chấm, mức gợi ý, mastery, lịch sử hỗ trợ, KG/RAG hay mã bài (plan §18.1)."""
    sc = SCENARIOS["SC-08"]  # Full ở đây backtrack theo KG, có giả thuyết lỗi và mastery
    sent = json.loads(build_input(turn("SC-08"), []))
    assert set(sent) == {"problem", "student_action", "student_work", "student_message", "previous_tutor_messages",
                         "feedback"}
    assert sent["problem"] == problem_prompt("E02-P001") and sent["student_work"] == list(sc.state.latest_submission)
    assert sent["student_action"] == "submit" and sent["previous_tutor_messages"] == []
    model = baseline(GOOD)
    model.run(turn("SC-08"))
    request = model.client.requests[0]
    everything = request["instructions"] + request["input"]
    for hidden in ("verified_incorrect", "first_error_step", "error_family", "hint_level", "mastery",
                   "PRE-", "E02-P001", "x=8", "x = 8", *(k.skill_id for k in sc.state.skills)):
        assert hidden not in everything, hidden


def test_only_the_last_tutor_messages_of_the_window_are_sent():
    messages = tuple(f"Câu {n}" for n in range(1, 6))
    window = BaselineTurn.from_state(SCENARIOS["SC-01"].state, problem_prompt, messages)
    assert window.previous_messages == ("Câu 3", "Câu 4", "Câu 5")  # cùng REPEAT_WINDOW với generator


# --------------------------------------------------------------------------- cùng policy về tiết lộ

def test_a_leaked_answer_is_regenerated_with_the_reason_and_never_with_the_answer():
    model = baseline(LEAK, GOOD)
    outcome = model.run(turn("SC-01"))
    first, second = outcome.attempts
    assert Check.ANSWER_LEAK in first.violations and not first.accepted
    assert second.accepted and outcome.final_source == "llm" and outcome.message == GOOD
    assert outcome.regenerations_used == 1 and first.usage.prompt_version == PROMPT_VERSION
    feedback = json.loads(model.client.requests[1]["input"])["feedback"]
    assert "answer_leak" in {f["code"] for f in feedback} and "8" not in json.dumps(feedback)


def test_a_message_that_still_leaks_after_the_regeneration_is_replaced_by_the_system_message():
    outcome = baseline(LEAK, "Đáp số: x = 8.").run(turn("SC-01"))
    assert len(outcome.attempts) == 2 and not any(a.accepted for a in outcome.attempts)
    assert outcome.final_source == "system" and outcome.message == SYSTEM_MESSAGE


def test_writing_the_corrected_step_counts_as_giving_away_the_solution():
    outcome = baseline("Bước 1 phải là 2x - 6 = 10 mới đúng.", GOOD).run(turn("SC-01"))
    assert Check.UNSOURCED_EQUATION in outcome.attempts[0].violations and outcome.message == GOOD


def test_listing_the_solution_steps_in_words_is_rejected_as_in_the_system():
    """Ca từ review: câu này qua baseline trong khi Full chặn (tests/test_generation.py, GN-01)."""
    plan = "Em hãy nhân hai với từng số hạng trong ngoặc, cộng sáu vào hai vế rồi chia hai để tìm nghiệm nhé."
    model = baseline(plan, GOOD)
    outcome = model.run(turn("SC-01"))
    assert outcome.attempts[0].violations == [Check.HINT_LEVEL_EXCEEDED] and outcome.message == GOOD
    (feedback,) = json.loads(model.client.requests[1]["input"])["feedback"]
    assert feedback["code"] == "hint_level_exceeded" and "hint_level" not in feedback["fix"]
    # Một thao tác, hay thao tác đề đã nhắc, thì không bị chặn: baseline không có mức hint.
    assert baseline("Em thử nhân 2 vào từng số hạng trong ngoặc nhé.").run(turn("SC-01")).final_source == "llm"


def test_a_verifier_error_keeps_the_drafted_message_and_its_usage(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("verifier exploded")

    monkeypatch.setattr(VERIFIER, "solution_checks", broken)
    row = run_turn(SCENARIOS["SC-01"], SOCRATIC_LLM, Models.fake())
    assert row["error"] == "RuntimeError: verifier exploded" and row["model_calls"] == 1
    (attempt,) = row["attempts"]
    assert attempt["message"] == EchoBaseline.MESSAGE and not attempt["accepted"]
    assert len(row["generation_usages"]) == 1 and "message" not in row
    assert summarize([row])["configurations"][SOCRATIC_LLM]["model_calls_without_usage"] == 0


def test_confirming_an_answer_the_student_found_alone_is_not_a_leak():
    praise = "Em làm đúng rồi, x = 8 thỏa mãn phương trình."
    outcome = baseline(praise).run(turn("SC-10"))  # học sinh tự giải đúng, đã xác minh
    assert outcome.final_source == "llm" and outcome.message == praise and outcome.attempts[0].violations == []


def test_a_right_answer_after_a_wrong_step_cannot_be_confirmed():
    """Ca từ review: đáp án đúng nhưng bước khai triển sai. Validator chấm từng bước nên bài là
    verified_incorrect; xác nhận "x = 8" lúc này là nói cho học sinh biết đáp án."""
    lucky = BaselineTurn(problem_id="E02-P001", problem_prompt=problem_prompt("E02-P001"), trigger="submit",
                         submission=("2x - 3 = 10", "x = 8"), student_message=None, solved_current=False)
    model = baseline("Em làm đúng rồi, x = 8 là đúng.", GOOD)
    outcome = model.run(lucky)
    assert Check.ANSWER_LEAK in outcome.attempts[0].violations and outcome.message == GOOD
    assert "hint at the final answer" in model.client.requests[0]["instructions"]
    assert "even when the final answer happens to be correct" in model.client.requests[0]["instructions"]


def test_without_an_answer_key_the_model_is_not_called():
    model = baseline(GOOD, verifier=ResponseVerifier(lambda problem_id: None))
    outcome = model.run(turn("SC-01"))
    assert outcome.llm_skipped_reason == "answer_key_missing" and outcome.attempts == ()
    assert outcome.message == SYSTEM_MESSAGE and model.client.requests == []


@pytest.mark.parametrize("output, error", [(LLMCallFailed("APIConnectionError", 12.0), "APIConnectionError"),
                                           (LLMCall(text="không phải JSON", model_id="fake-llm", input_tokens=9,
                                                    cached_input_tokens=0, output_tokens=3, latency_ms=1.0),
                                            "invalid_output")])
def test_a_failed_call_is_logged_with_its_usage_and_not_retried(output, error):
    model = baseline(output, GOOD)
    outcome = model.run(turn("SC-01"))
    (attempt,) = outcome.attempts
    assert attempt.message is None and attempt.usage.error == error
    assert outcome.final_source == "system" and len(model.client.requests) == 1


# --------------------------------------------------------------------------- trong lô ablation

def test_the_baseline_runs_beside_the_configurations_on_the_same_scenarios():
    models = Models.fake()
    rows = run_ablation([SCENARIOS["SC-01"], SCENARIOS["SC-13"]], ["full", SOCRATIC_LLM], models)
    assert [(r["scenario"], r["configuration"]) for r in rows] == [
        ("SC-01", "full"), ("SC-01", SOCRATIC_LLM), ("SC-13", "full"), ("SC-13", SOCRATIC_LLM)]
    ours = [r for r in rows if r["configuration"] == SOCRATIC_LLM]
    for r in ours:
        assert r["decision"] is None and r["agent_usage"] is None and r["error"] is None
        assert r["model_calls"] == len(r["generation_usages"]) == 1 and r["message"] == EchoBaseline.MESSAGE
    s = summarize(rows)["configurations"][SOCRATIC_LLM]
    assert (s["final_acceptable"], s["gate_rejected"], s["action"]["differs_from_full"]) == (None, None, None)
    assert s["response_sources"] == {"llm": 2} and s["agent"]["llm_calls"] == 0
    outputs = [o for o in system_outputs(rows) if o.system == SOCRATIC_LLM]
    assert len(outputs) == 2 and all(o.action is None and o.response_source == "llm" for o in outputs)


def test_wording_checks_the_system_enforces_are_only_recorded_for_the_baseline(monkeypatch):
    message = "Bước 2 đúng rồi. Em xem lại bước 1 nhé?"
    monkeypatch.setattr(EchoBaseline, "MESSAGE", message)
    row = run_turn(SCENARIOS["SC-01"], SOCRATIC_LLM, Models.fake())
    assert row["message"] == message and row["response_source"] == "llm"
    assert row["unenforced_checks"] == [Check.UNVERIFIED_AFFIRMATION]
    assert summarize([row])["configurations"][SOCRATIC_LLM]["unenforced_checks"] == {"unverified_affirmation": 1}
