"""Sinh và kiểm tra phản hồi: đọc toán trong câu, verifier, chuỗi LLM → sinh lại → template, graph."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.agent.decision import DecisionConfig  # noqa: E402
from app.agent.graph import Services, TurnInput, TutorEngine  # noqa: E402
from app.agent.stubs import demo_answer_key  # noqa: E402
from app.generation.contracts import Check, ResponseAttempt, ResponseRecord  # noqa: E402
from app.generation.equivalence import linear_equivalent  # noqa: E402
from app.generation.llm_generator import LLMResponseGenerator, build_input  # noqa: E402
from app.generation.math_text import equalities, implied_equalities, sides  # noqa: E402
from app.generation.responder import Responder  # noqa: E402
from app.generation.templates import SYSTEM_MESSAGE, TemplateGenerator  # noqa: E402
from app.generation.verifier import MAX_MESSAGE_CHARS, ResponseVerifier  # noqa: E402
from app.generation.wording import affirms_correctness, clauses, operations  # noqa: E402
from app.llm.client import LLMTimeout  # noqa: E402
from app.llm.fakes import FakeLLMClient  # noqa: E402
from research.generation.evaluate_generation import (  # noqa: E402
    check_verifier, evaluate, load_cases, main, oracle_client, summarize, summarize_verifier,
)

CASES = {c.id: c for c in load_cases()}
VERIFIER = ResponseVerifier(demo_answer_key)
WRONG = ["2x - 3 = 10", "2x = 13", "x = 6.5"]


def inp(case_id, previous=()):
    return CASES[case_id].input(tuple(previous))


def say(message, used=()):
    return {"message": message, "content_ids_used": list(used)}


def found(case_id, message, used=(), previous=()):
    return {c.value for c in VERIFIER.check_generated(inp(case_id, previous), message, list(used))}


def responder(outputs, templates=None, verifier=VERIFIER):
    client = FakeLLMClient(outputs)
    return Responder(templates or TemplateGenerator(), verifier, LLMResponseGenerator(client)), client


# --------------------------------------------------------------------------- đọc toán trong câu

def test_words_arrows_and_punctuation_end_a_math_run():
    text = "Ví dụ: 4x + 1 = 9 → trừ 1 ở hai vế: 4x = 8."
    assert equalities(text) == {frozenset({"4x+1", "9"}), frozenset({"4x", "8"})}


def test_bang_is_an_equals_sign_only_between_expressions():
    assert equalities("Em có 2x bằng 16 rồi") == {frozenset({"2x", "16"})}
    assert equalities("Em xem hai vế có bằng nhau không") == set()
    assert equalities("Tổng của một số và 5 bằng 12.") == {frozenset({"5", "12"})}


def test_question_with_empty_side_asserts_nothing():
    assert equalities("2 · (-3) = ?") == set()
    assert sides("2 · (-3) = ?") == {"2(-3)"}


def test_multiplication_signs_before_a_letter_or_bracket_are_dropped():
    assert sides("2 × (x − 3) và 3·a + 3·2") == {"2(x-3)", "3a+3*2"}


def test_a_chain_in_a_source_implies_every_pair():
    pairs = implied_equalities(["Ví dụ: 3(a + 2) = 3·a + 3·2 = 3a + 6."])
    assert frozenset({"3(a+2)", "3a+6"}) in pairs
    assert equalities("3(a + 2) = 3a + 6") <= pairs


# --------------------------------------------------------------------------- verifier: lộ đáp án

@pytest.mark.parametrize("message", [
    "Đáp án là x = 8.", "X=8 nhé", "Em nghĩ 8 = x không?", "Vậy x bằng 8.", "Nghiệm là 8.",
    "Đáp số: 8", "Kết quả của phương trình là 8.", "x là 8 đó",
])
def test_final_answer_is_caught_in_symbols_and_words(message):
    assert "answer_leak" in found("GN-01", message)


@pytest.mark.parametrize("message", [
    "Em thử x = 80 xem sao", "Nếu 2x = 8 thì sao?", "Em thay x = 6.5 vào đề nhé.", "x là ẩn, 2x = 8 thì sao?",
    "Bước 8 của em đâu?", "Nghiệm là số nào nhỉ?",
])
def test_other_numbers_are_not_the_answer(message):
    assert "answer_leak" not in found("GN-01", message)


def test_student_who_solved_it_may_hear_their_answer_confirmed():
    # SC-10: học sinh đã tự giải đúng bài đang làm (x = 8); bài kiểm tra mới E02-P003 có nghiệm x = 5.
    assert found("GN-10", "Đúng rồi, em tìm được x = 8!") == set()
    assert "answer_leak" in found("GN-10", "Bài mới có nghiệm x = 5 đấy.")


def test_expression_answers_compare_whole_sides():
    # SC-08 giao bài ôn A02-P001 "Khai triển -2(3y + 4)" có đáp án -6y - 8.
    assert "answer_leak" in found("GN-08", "Kết quả là -6y − 8 nhé.")
    assert "answer_leak" not in found("GN-08", "Nếu em được -6y + 8 thì xem lại dấu nhé.")


@pytest.mark.parametrize("message", [
    "Nghiệm là 16/2.", "x = 4·2 nhé", "Đáp số: 2^3", "Nghiệm của phương trình 2x = 16 là 8.", "8,0 = x đó",
])
def test_equivalent_forms_of_the_answer_are_caught(message):
    # Ca hồi quy từ review: "Nghiệm là 16/2." từng được gửi vì chỉ so chuỗi.
    assert "answer_leak" in found("GN-01", message)


def test_expression_answers_are_compared_by_value_but_quoting_the_problem_is_allowed():
    assert "answer_leak" in found("GN-08", "Em có ra -8 - 6y không?")
    assert "answer_leak" not in found("GN-08", "Bài ôn: Khai triển -2(3y + 4).")  # tương đương đáp án nhưng là đề


def test_math_the_verifier_cannot_read_is_unverified_not_accepted():
    for message in ("Em có biết nghiệm là √64 không?", "Nghiệm là 2 mũ 3 phải không?", "Có phải x ≤ 9 không?"):
        assert "math_unverified" in found("GN-01", message), message
    assert "math_unverified" not in found("GN-01", "Em bình tĩnh nhé, căn cứ vào bước 1 em thấy gì?")
    assert "math_unverified" not in found("GN-12", "Bài mới: Tổng của một số và 5 bằng 12. Lập phương trình và tìm số đó.")


def test_linear_equivalence_and_its_limits():
    assert linear_equivalent("16/2", "8") and linear_equivalent("-8-6y", "-6y-8")
    assert linear_equivalent("2(x-3)", "2x-6") and linear_equivalent("2^3", "8")
    assert linear_equivalent("x", "8") is False
    for unsupported in ("x(x+1)", "8/(x-x)", "2^x", "x^2", "2x-", "8/0", "-" * 2000 + "8"):
        assert linear_equivalent(unsupported, "8") is None, unsupported[:20]


def test_unary_minus_binds_looser_than_power():
    # Ca hồi quy từ review: -2^2 từng được tính là 4, nên "-2^2 + 12" (= 8) lọt qua.
    assert linear_equivalent("-2^2", "-4") and linear_equivalent("(-2)^2", "4")
    assert linear_equivalent("-2^2+12", "8") and linear_equivalent("2^3^2", "512")
    assert linear_equivalent("2(3)^2", "18") and linear_equivalent("-(2)^2", "-4")
    assert "answer_leak" in found("GN-01", "Nghiệm là -2^2 + 12, em thấy sao?")


def test_template_fallbacks_of_every_case_pass_the_leak_check():
    templates = TemplateGenerator()
    for case_id in CASES:
        i = inp(case_id)
        assert VERIFIER.check_template(i, templates(i)) == [], case_id
        assert VERIFIER.check_template(i, templates.safe(i.decision)) == [], case_id


# --------------------------------------------------------------------------- verifier: các kiểm tra khác

def test_equations_must_come_from_what_the_generator_was_given():
    assert found("GN-01", "Em viết 2x - 3 = 10 ở bước 1, vì sao vậy?") == set()          # bài làm của học sinh
    assert found("GN-01", "Đề là 2(x - 3) = 10, đề hỏi gì nhỉ?") == set()                # đề bài
    assert found("GN-07", "Ví dụ khác: 3(a + 2) = 3a + 6.", ["KB-A02-EXAMPLE-01"]) == set()  # nội dung
    assert found("GN-01", "Ta có 2(x - 3) = 2x - 6 mà, em thấy sao?") == {"unsourced_equation",
                                                                            "unsourced_expression"}


def test_new_expressions_with_an_unknown_are_steps_the_student_must_write():
    assert found("GN-06", "Bước 1 phải là 2x - 6 nhé.") == {"unsourced_expression"}          # mức 2
    assert found("GN-07", "Em viết lại thành 2x - 6 nhé.", ["KB-A02-EXAMPLE-01"]) == {"unsourced_expression"}  # mức 3
    # Một phần của biểu thức có trong nguồn, và biểu thức không có biến, đều được dùng.
    assert found("GN-01", "Trong ngoặc x - 3 có hai số hạng; 2 · (-3) bằng bao nhiêu?") == set()


def test_content_and_shape_checks():
    assert found("GN-06", "Em xem lại bước 1 nhé.", ["KB-A02-HINT-01", "KB-X"]) == {"unknown_content"}
    assert found("GN-07", "Em làm lại bước 1 nhé.") == {"missing_content"}
    assert found("GN-01", "Em làm gì ở bước 1? Vì sao?") == {"too_many_questions"}
    assert found("GN-01", "Em xem lại bước 1 nhé. " * 30 + "Em thấy gì?") == {"too_long"}
    assert len("Em xem lại bước 1 nhé. " * 30) > MAX_MESSAGE_CHARS
    assert found("GN-01", "Em thấy  bước 1 thế nào?", previous=["em thấy bước 1 thế nào?"]) == {"repeated_message"}
    assert found("GN-01", "Em xem lại bước 1 nhé.") == {"missing_question"}  # diagnose phải hỏi


def test_quoting_a_wrong_step_is_allowed_but_calling_it_correct_is_not():
    # Ca hồi quy từ review: phương trình có trong bài làm nên từng được nhận, kèm lời khẳng định nó đúng.
    assert found("GN-01", "Bước 2x − 3 = 10 của em là phép khai triển đúng. Bước 2 em làm thế nào?") \
        == {"unverified_affirmation"}
    assert found("GN-01", "Em viết 2x − 3 = 10 ở bước 1, em kiểm tra xem có đúng không?") == set()
    for fine in ("Bước 1 chưa đúng, em xem lại chỗ nào?", "Đúng là bước 1 cần xem lại, em thấy chỗ nào?"):
        assert "unverified_affirmation" not in found("GN-01", fine), fine
    assert "unverified_affirmation" not in found("GN-10", "Đúng rồi, em tìm được x = 8!")  # đã xác minh đúng


def test_hint_level_limits_how_much_of_the_method_is_told():
    # Ca hồi quy từ review: ở lượt chẩn đoán mức 0, câu kể gần hết cách giải từng được gửi.
    plan = "Em hãy nhân hai với từng số hạng trong ngoặc, rồi cộng sáu vào hai vế và chia hai để tìm nghiệm."
    assert "hint_level_exceeded" in found("GN-01", plan)
    assert "hint_level_exceeded" in found("GN-04", "Em cộng 6 vào hai vế của bước 1 rồi kiểm tra lại nhé.")  # mức 1
    assert found("GN-01", "Ở bước 1, em đã nhân 2 với những số hạng nào?") == set()     # hỏi về thao tác thì được
    assert found("GN-06", "Bước 1 cần xem lại: em nhân số ngoài ngoặc với từng số hạng nhé.",
                 ["KB-A02-HINT-01"]) == set()                                           # thao tác có trong nội dung
    # Mức 3 được thêm một thao tác, không được kể chuỗi thao tác.
    assert "hint_level_exceeded" not in found("GN-07", "Em nhân 2 vào ngoặc rồi chuyển vế nhé.", ["KB-A02-EXAMPLE-01"])
    assert "hint_level_exceeded" in found("GN-07", "Em cộng 6 vào hai vế rồi chia cho 2 nhé.", ["KB-A02-EXAMPLE-01"])
    assert "hint_level_exceeded" not in found("GN-07", "Mình chia nhỏ bước 1 nhé: phép nhân ở đây áp cho mấy số hạng?",
                                              ["KB-A02-EXAMPLE-01"])


def test_wording_helpers():
    assert affirms_correctness("Bước 2 em làm đúng rồi.") and affirms_correctness("Kết quả chính xác.")
    assert not affirms_correctness("Bước 2 có đúng không?") and not affirms_correctness("Bước 2 chưa đúng.")
    assert operations("Em nhân 2 với x. Em chia cho 2 được không?") == [("nhân", False), ("chia", True)]
    assert operations("Phép nhân ở đây, mình chia nhỏ ra, trừ khi em muốn.") == []


def test_a_question_mark_does_not_exempt_the_other_clauses():
    # Ca hồi quy từ review: dấu "?" cuối câu từng miễn kiểm tra cho cả câu.
    assert affirms_correctness("Bước 2x − 3 = 10 của em đúng rồi, em làm bước tiếp theo thế nào?")
    assert affirms_correctness("Vì sao bước 2 của em đúng?")  # hỏi "vì sao đúng" vẫn là khẳng định
    assert operations("Em hãy cộng sáu vào hai vế nhé, em hiểu chưa?") == [("cộng", False)]
    assert operations("Em thử cộng 6 vào hai vế xem được gì?") == [("cộng", False)]  # lời bảo làm trong câu hỏi
    # Mệnh đề phụ "khi ..." thuộc câu hỏi phía sau; số thập phân "6,5" không tách mệnh đề.
    assert operations("Khi nhân một số với ngoặc, em nhân số đó với những phần nào?") == [("nhân", True),
                                                                                         ("nhân", True)]
    assert len(clauses("Em thay x = 6,5 vào đề, hai vế có bằng nhau không?")) == 2
    assert found("GN-01", "Bước 2x − 3 = 10 của em đúng rồi, em làm bước tiếp theo thế nào?") \
        == {"unverified_affirmation"}
    assert found("GN-01", "Em hãy cộng sáu vào hai vế nhé, em hiểu chưa?") == {"hint_level_exceeded"}


def test_dev_set_verifier_labels_and_oracles():
    rows = check_verifier(list(CASES.values()), VERIFIER)
    s = summarize_verifier(rows)
    assert s["exact"] == s["items"] and s["oracle_passed"] == s["oracles"] == len(CASES)
    assert all(c["fp"] == 0 and c["fn"] == 0 for c in s["per_check"].values())


# --------------------------------------------------------------------------- generator: input

def test_generator_input_has_no_answer_and_no_identity():
    for case_id, case in CASES.items():
        i = inp(case_id)
        payload = build_input(i, [])
        compact = payload.replace(" ", "").lower()
        for pid in VERIFIER.problems_to_check(i):
            for form in demo_answer_key(pid).final_answers:
                assert form not in compact, (case_id, pid)
        state = case.scenario.state
        assert state.student_id not in payload and str(state.session_id) not in payload
        assert json.loads(payload)["decision"]["intent"] == i.decision.intent.value


def test_generator_only_sees_content_the_decision_cites():
    payload = json.loads(build_input(inp("GN-07"), []))
    assert [c["content_id"] for c in payload["content"]] == ["KB-A02-EXAMPLE-01"]
    assert json.loads(build_input(inp("GN-01"), []))["content"] == []


# --------------------------------------------------------------------------- chuỗi sinh phản hồi

GOOD = say("Ở bước 1, em đã nhân 2 với những số hạng nào trong ngoặc?")
LEAK = say("Đáp án là x = 8, em thấy sao?")


TWO_QUESTIONS = say("Em có nhớ quy tắc phân phối không? Khi nhân một số với một biểu thức trong ngoặc, "
                    "em cần làm gì với từng phần trong ngoặc?")
ONE_QUESTION = say("Khi nhân một số với một biểu thức trong ngoặc, em cần làm gì với từng phần trong ngoặc?")


def test_two_question_drafts_from_the_real_run_get_a_concrete_fix():
    # Lượt chạy thật trên dev: 35/41 lỗi là hỏi hai câu (câu mở "Em có nhớ ... không?" rồi mới hỏi
    # thật), và sinh lại chỉ sửa được 10/25 lượt.
    assert found("GN-15", TWO_QUESTIONS["message"]) == {"too_many_questions"}
    assert not found("GN-15", ONE_QUESTION["message"])
    r, client = responder([TWO_QUESTIONS, ONE_QUESTION])
    out = r.run(inp("GN-15"))
    assert out.final_source == "llm" and out.message == ONE_QUESTION["message"]
    feedback = json.loads(client.requests[1]["input"])["feedback"]
    assert [f["code"] for f in feedback] == ["too_many_questions"]
    assert "exactly one" in feedback[0]["fix"] and "Em có nhớ" in feedback[0]["fix"]
    assert "at most one question mark" in client.requests[0]["instructions"]


def test_prerequisite_probe_names_the_topic_it_asks_about():
    # Lượt chạy thật: câu template của probe_prerequisite chỉ nói "quy tắc nền của dạng bài này".
    i = inp("GN-15")
    assert i.decision.intent == "probe_prerequisite" and not i.content
    assert i.target_skill_title == "Tính phân phối"
    message = TemplateGenerator()(i)
    assert '"Tính phân phối"' in message and message.count("?") == 1
    assert json.loads(build_input(i, []))["target_skill"] == "Tính phân phối"
    # Không biết tên chủ đề (skill ngoài registry) thì dùng câu chung như trước.
    unnamed = TemplateGenerator()(replace(i, target_skill_title=None))
    assert "Tính phân phối" not in unnamed and unnamed == TemplateGenerator().safe(i.decision)


def test_naming_the_target_topic_is_not_telling_the_method():
    # Tên chủ đề có thể chứa tên phép toán; nhắc tên chủ đề ở lượt hỏi không phải là bảo cách làm.
    named = replace(inp("GN-15"), target_skill_title="Nhân chia số có dấu")
    unnamed = replace(named, target_skill_title=None)
    for message in ('Mình hỏi lại về phần "Nhân chia số có dấu" nhé: tích của hai số âm mang dấu gì?',
                    "Mình hỏi lại về phần “nhân chia  số có dấu” nhé: tích của hai số âm mang dấu gì?"):
        assert not VERIFIER.check_generated(named, message, [])
        assert VERIFIER.check_generated(unnamed, message, []) == [Check.HINT_LEVEL_EXCEEDED]
    # Thiếu ngoặc kép hoặc thiếu danh từ gọi tên thì không chắc đó là tên: vẫn xét như chữ thường
    # (chặn nhầm theo hướng an toàn).
    for plain in ("Mình hỏi lại về phần Nhân chia số có dấu nhé: tích của hai số âm mang dấu gì?",
                  'Mình hỏi lại về "Nhân chia số có dấu" nhé: tích của hai số âm mang dấu gì?'):
        assert VERIFIER.check_generated(named, plain, []) == [Check.HINT_LEVEL_EXCEEDED]
    # Review: tên chủ đề không biến phép toán trong tên thành "đã cho". Bảo học sinh làm chính phép
    # toán đó, hay một phép toán khác, ở mức hint 0 vẫn bị chặn, có nhắc tên chủ đề hay không.
    for told in ("Em hãy nhân 2 với từng số hạng trong ngoặc nhé, em thấy sao?",
                 "Về phần Nhân chia số có dấu: em hãy nhân 2 với từng số hạng trong ngoặc nhé, em thấy sao?",
                 "Em hãy cộng 6 vào hai vế nhé, phần Nhân chia số có dấu em còn nhớ không?"):
        assert Check.HINT_LEVEL_EXCEEDED in VERIFIER.check_generated(named, told, []), told
        assert Check.HINT_LEVEL_EXCEEDED in VERIFIER.check_generated(unnamed, told, []), told


@pytest.mark.parametrize("message", [
    "Em hãy thu gọn hạng tử đồng dạng ở vế trái nhé, em hiểu chưa?",     # ca của review
    "Em thu gọn hạng tử đồng dạng ở vế trái nhé, em hiểu chưa?",         # bảo làm, không có từ mệnh lệnh
    'Em hãy "thu gọn hạng tử đồng dạng" ở vế trái nhé, em hiểu chưa?',   # ngoặc kép nhưng là lời bảo làm
    'Em "thu gọn hạng tử đồng dạng" ở vế trái nhé, em hiểu chưa?',       # ngoặc kép, không đứng sau "phần"
    'Em hãy làm phần "thu gọn hạng tử đồng dạng" ở vế trái nhé, em hiểu chưa?',  # đủ dạng tên nhưng sau "hãy"
])
def test_an_instruction_that_reuses_the_topic_name_is_still_an_instruction(message):
    # Review: tên concept thật "Thu gọn hạng tử đồng dạng" cũng là một thao tác. Cụm đó trong lời
    # bảo làm phải bị chặn ở mức hint 0, dù generator có được cho tên chủ đề hay không.
    named = replace(inp("GN-15"), target_skill_title="Thu gọn hạng tử đồng dạng")
    assert Check.HINT_LEVEL_EXCEEDED in VERIFIER.check_generated(named, message, [])
    assert Check.HINT_LEVEL_EXCEEDED in VERIFIER.check_generated(replace(named, target_skill_title=None), message, [])


def test_naming_that_topic_in_a_question_is_allowed():
    named = replace(inp("GN-15"), target_skill_title="Thu gọn hạng tử đồng dạng")
    assert not VERIFIER.check_generated(named, 'Ở phần "Thu gọn hạng tử đồng dạng", hai hạng tử thế nào thì gộp được?', [])


def test_accepted_llm_message_is_sent():
    r, client = responder([GOOD])
    out = r.run(inp("GN-01"))
    assert out.final_source == "llm" and out.message == GOOD["message"] and len(client.requests) == 1
    record = out.record(uuid4(), uuid4())
    assert record.regenerations_used == 0 and record.prompt_version and record.attempts[0].usage


def test_rejected_message_is_regenerated_once_with_feedback_and_no_answer():
    r, client = responder([LEAK, GOOD])
    out = r.run(inp("GN-01"))
    assert out.final_source == "llm" and out.message == GOOD["message"]
    assert [a.violations for a in out.attempts] == [["answer_leak", "unsourced_equation"], []]
    second = json.loads(client.requests[1]["input"])
    assert [f["code"] for f in second["feedback"]] == ["answer_leak", "unsourced_equation"]
    assert "x = 8" not in client.requests[1]["input"]  # bản nháp lộ đáp án không được gửi lại
    assert out.record(uuid4(), uuid4()).regenerations_used == 1


def test_still_rejected_after_regeneration_falls_back_to_template():
    r, client = responder([LEAK, LEAK])
    out = r.run(inp("GN-01"))
    assert [a.source for a in out.attempts] == ["llm", "llm", "template"]
    assert out.final_source == "template_fallback" and "8" not in out.message and len(client.requests) == 2


@pytest.mark.parametrize("output, check", [
    (LLMTimeout(8000.0), Check.LLM_UNAVAILABLE),
    ("not json", Check.LLM_INVALID_OUTPUT),
    ({"message": "", "content_ids_used": []}, Check.LLM_INVALID_OUTPUT),
])
def test_call_failures_go_straight_to_template(output, check):
    r, client = responder([output])
    out = r.run(inp("GN-01"))
    assert [(a.source, a.violations) for a in out.attempts] == [("llm", [check]), ("template", [])]
    assert out.final_source == "template_fallback" and len(client.requests) == 1
    assert out.attempts[0].usage is not None  # chi phí lần gọi lỗi vẫn được ghi


def test_no_regeneration_without_budget():
    r, _ = responder([LEAK])
    attempts = [r.draft(inp("GN-01"), [])]
    attempts, out = r.settle(inp("GN-01"), attempts, may_regenerate=False)
    assert out is not None and out.final_source == "template_fallback"


def test_missing_answer_key_skips_the_llm():
    keys = {"E02-P001": None}
    verifier = ResponseVerifier(lambda pid: keys.get(pid, demo_answer_key(pid)))
    r, client = responder([GOOD], verifier=verifier)
    out = r.run(inp("GN-01"))
    assert client.requests == [] and out.final_source == "template_fallback"
    record = out.record(uuid4(), uuid4())
    assert record.llm_skipped_reason == "answer_key_missing" and record.prompt_version is None


class LeakingTemplates(TemplateGenerator):
    def __call__(self, inp):
        return "Đáp án: x = 8."

    def safe(self, p):
        return "x = 8"


def test_system_message_when_nothing_passes():
    r, _ = responder([LEAK, LEAK], templates=LeakingTemplates())
    out = r.run(inp("GN-01"))
    assert [a.source for a in out.attempts] == ["llm", "llm", "template", "template_safe"]
    assert out.final_source == "system" and out.message == SYSTEM_MESSAGE
    assert out.record(uuid4(), uuid4()).final_source == "system"


def test_record_rejects_inconsistent_traces():
    ok = ResponseAttempt(source="template", message="Chào em.", accepted=True)
    rejected = ResponseAttempt(source="template", message="x = 8", violations=[Check.ANSWER_LEAK])
    base = dict(turn_id=uuid4(), decision_id=uuid4(), template_version="t", verifier_version="v")
    assert ResponseRecord(**base, attempts=[ok], final_source="template", message="Chào em.")
    with pytest.raises(ValueError):  # câu được nhận phải là lần sinh cuối
        ResponseRecord(**base, attempts=[ok, rejected], final_source="template", message="Chào em.")
    with pytest.raises(ValueError):  # nguồn không khớp các lần sinh
        ResponseRecord(**base, attempts=[rejected, ok], final_source="template", message="Chào em.")
    llm = ResponseAttempt(source="llm", violations=[Check.LLM_UNAVAILABLE])
    with pytest.raises(ValueError):  # quá một lần sinh lại
        ResponseRecord(**base, prompt_version="p", attempts=[llm, llm, llm, ok], final_source="template_fallback",
                       message="Chào em.")
    with pytest.raises(ValueError):  # có gọi LLM thì phải có prompt_version
        ResponseRecord(**base, attempts=[llm, ok], final_source="template_fallback", message="Chào em.")
    with pytest.raises(ValueError):  # lần sinh lỗi phải nói vì sao
        ResponseAttempt(source="llm")


# --------------------------------------------------------------------------- trong LangGraph

def config():
    return DecisionConfig(configuration="rule_policy", policy_version="rule-policy-test")


def engine(outputs, **services):
    client = FakeLLMClient(outputs)
    return TutorEngine(config(), Services(response_generator=LLMResponseGenerator(client), **services)), client


def submit(eng, sid, steps=WRONG, request_id=None):
    return eng.turn(sid, TurnInput(request_id=request_id or uuid4(), trigger="submit", steps=list(steps)))


def test_graph_sends_the_llm_message_and_logs_it():
    eng, _ = engine([GOOD])
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = submit(eng, sid)
    assert reply.response_source == "llm" and reply.message == GOOD["message"]
    record = eng.responses(sid)[0]
    assert record.decision_id == reply.decision_id and record.final_source == "llm"
    assert eng.decisions(sid)[0].regenerations_used == 0


def test_graph_regenerates_once_and_records_it_in_the_decision():
    eng, client = engine([LEAK, GOOD])
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = submit(eng, sid)
    assert reply.message == GOOD["message"] and len(client.requests) == 2
    assert eng.decisions(sid)[0].regenerations_used == 1
    assert [a.accepted for a in eng.responses(sid)[0].attempts] == [False, True]


class FailingOnceVerifier(ResponseVerifier):
    failed = False

    def check_generated(self, *args):
        if not self.failed:
            self.failed = True
            raise RuntimeError("verifier down")
        return super().check_generated(*args)


def test_retry_after_verify_failure_does_not_call_the_llm_again():
    eng, client = engine([GOOD], verifier=FailingOnceVerifier(demo_answer_key))
    sid = eng.start("demo-a", "E02-P001").session_id
    request_id = uuid4()
    with pytest.raises(RuntimeError, match="verifier down"):
        submit(eng, sid, request_id=request_id)
    reply = submit(eng, sid, request_id=request_id)
    assert reply.response_source == "llm" and len(client.requests) == 1


def test_previous_tutor_messages_prevent_verbatim_repeats():
    same = say("Em xem lại bước 1 giúp mình được không?")
    eng, _ = engine([same, same, say("Mình cùng nhìn lại bước 1 nhé, em thấy gì?")])
    sid = eng.start("demo-a", "E02-P001").session_id
    submit(eng, sid)
    reply = submit(eng, sid)
    assert reply.message == "Mình cùng nhìn lại bước 1 nhé, em thấy gì?"
    assert eng.responses(sid)[1].attempts[0].violations == ["repeated_message"]


@pytest.mark.parametrize("bad", [
    "Nghiệm là 16/2.",
    "Bước 2x − 3 = 10 của em là phép khai triển đúng.",
    "Em hãy nhân hai với từng số hạng trong ngoặc, rồi cộng sáu vào hai vế và chia hai để tìm nghiệm.",
    "Nghiệm là -2^2 + 12, em thấy sao?",
    "Bước 2x − 3 = 10 của em đúng rồi, em làm bước tiếp theo thế nào?",
    "Em hãy cộng sáu vào hai vế nhé, em hiểu chưa?",
])
def test_review_messages_never_reach_the_student(bad):
    # Ca hồi quy cho hai lần review, qua đường gửi phản hồi cuối: LLM viết câu lỗi cả hai lần.
    eng, client = engine([say(bad), say(bad)])
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = submit(eng, sid)
    assert reply.action == "diagnose" and reply.hint_level == 0
    assert reply.message != bad and reply.response_source == "template_fallback" and len(client.requests) == 2
    assert all(not a.accepted for a in eng.responses(sid)[0].attempts if a.source == "llm")


def test_template_path_is_unchanged_without_an_llm():
    eng = TutorEngine(config())
    sid = eng.start("demo-a", "E02-P001").session_id
    reply = submit(eng, sid)
    assert reply.response_source == "template"
    record = eng.responses(sid)[0]
    assert record.prompt_version is None and [a.source for a in record.attempts] == ["template"]


# --------------------------------------------------------------------------- script đánh giá

def test_fake_run_passes_every_case_on_the_first_try():
    client, before = oracle_client()
    rows = evaluate(list(CASES.values()), client, before)
    s = summarize(rows)
    assert s["first_accepted"] == s["cases"] == len(CASES) and s["final_sources"] == {"llm": len(CASES)}
    assert s["regenerated"] == 0 and s["llm_calls"] == len(CASES)


def test_openai_mode_refuses_without_confirmation(monkeypatch):
    monkeypatch.setattr("research.llm_support.read_env", lambda: {"LLM_ENABLED": "true", "OPENAI_API_KEY": "sk-test"})

    def forbidden(*args, **kwargs):
        raise AssertionError("must not build a real client")

    monkeypatch.setattr("research.llm_support.OpenAIResponsesClient", forbidden)
    assert main(["--llm", "openai"]) == 2
    assert main(["--llm", "openai", "--max-calls", "3", "--yes"]) == 2
    monkeypatch.setattr("research.llm_support.read_env", lambda: {})
    assert main(["--llm", "openai", "--yes"]) == 2
