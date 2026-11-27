"""Chế độ chấm đáp án cuối không tính bài chưa làm xong là đã làm đúng (backend/app/final_answer.py).

Trước khi sửa: chép lại đề ``5/12+7/18`` hoặc mới đi một bước ``x+3=5`` vẫn được chấm đúng, vì
validator chỉ so giá trị. Bài như vậy sẽ thành bằng chứng năng lực sai cho BKT.
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/authoring"))
from app import math_validator  # noqa: E402
from app.assessment_modes import ASSESSMENT_MODE  # noqa: E402
from app.authoring_runs import load_authoring_source  # noqa: E402
from app.curriculum import PilotBank  # noqa: E402
from app.final_answer import is_final_form, is_number  # noqa: E402
from prepare_member3_pilot import rendered_pilot  # noqa: E402


def grade(task, answer, prompt=None):
    problem = {"problem_id": "T", "concept_id": "X", "primary_skill_id": "SK-X", "assessment_mode": ASSESSMENT_MODE,
               "review": {"status": "human_approved"}, "task": task}
    if prompt is not None:
        problem["prompt"] = prompt
    return math_validator.validate(problem, [answer])["assessment"]


def status(kind, expression, answer, prompt=None):
    return grade({"kind": kind, "expression": expression}, answer, prompt)["assessment_status"]


@pytest.mark.parametrize("kind, expression, answer", [
    ("numeric", "5/12+7/18", "5/12+7/18"),            # N06 chép đề
    ("numeric", "5/12+7/18", "15/36+14/36"),          # N06 mới quy đồng
    ("numeric", "7/20+5/12", "46/60"),                # N06 chưa rút gọn
    ("numeric", "17+6*8", "17+6*8"),                  # N03 chép đề
    ("numeric", "(15-7)*4+36/(2+7)", "8*4+36/9"),     # N03 làm dở
    ("numeric", "(-13)*(-4)", "(-13)*(-4)"),          # N02 chép đề
    ("exp_log_equation", "exp; 2; x+3; 32", "x+3=5"),  # F10 mới bước đầu
    ("exp_log_equation", "log; 3; 2*x-1; 2", "2*x-1=9"),
    ("vieta", "other_root; x*x-11*x+18; 2", "x+2=11"),
    ("linear_equation", "x/3+5=9", "x/3+5=9"),         # E01 chép đề
    ("linear_equation", "x/3+5=9", "x/3=4"),
    ("log_value", "log; 2; 64", "2*3"),
    ("linear_inequality", "2*x-7<5", "x<12/2"),
    ("product_equation", "(x-6)*(x+4)", "{12/2; -4}"),
])
def test_unfinished_work_with_the_right_value_is_not_a_correct_answer(kind, expression, answer):
    assessment = grade({"kind": kind, "expression": expression}, answer)
    assert assessment["assessment_status"] == "unverified"
    assert assessment["reason_code"] == "valid_partial"


@pytest.mark.parametrize("kind, expression, answer", [
    ("numeric", "5/12+7/18", "29/36"),
    ("numeric", "120/(4+11)-3*(9-6)", "-1"),
    ("exp_log_equation", "exp; 2; x+3; 32", "x = 2"),
    ("vieta", "other_root; x*x-11*x+18; 2", "x=9"),
    ("linear_equation", "x/3+5=9", "x=12"),            # E01 chấm được ở chế độ đáp án cuối
    ("linear_equation", "x/3+5=9", "12"),
])
def test_finished_answers_are_still_correct(kind, expression, answer):
    assert status(kind, expression, answer) == "verified_correct"


def test_unfinished_work_with_a_wrong_value_is_still_wrong():
    assert status("numeric", "5/12+7/18", "12/30") == "verified_incorrect"
    assert status("exp_log_equation", "exp; 2; x+3; 32", "x+3=6") == "verified_incorrect"


@pytest.mark.parametrize("text, expected", [
    ("29/36", True), ("-7/24", True), ("-4", True), ("+5", True),
    ("0.325", False), ("46/60", False), ("4/1", False), ("3/-4", False), ("2*3", False), ("(-4)", False), ("", False),
])
def test_number_must_be_written_in_reduced_form(text, expected):
    assert is_number(text) is expected
    assert is_number("0.325", decimals=True) and not is_number("46/60", decimals=True)


def _banks():
    _, member2 = load_authoring_source("member2-v2")
    member3 = PilotBank.model_validate(rendered_pilot()[0]["draft-bank.json"])
    return [("Member 2", member2), ("Member 3", member3)]


BANKS = _banks()


@pytest.mark.parametrize("owner, bank", BANKS, ids=[owner for owner, _ in BANKS])
def test_every_authored_problem_rejects_copying_the_prompt_and_unfinished_steps(owner, bank):
    """Trên mọi bài đã duyệt (Member 2) và nháp (Member 3): đáp án chuẩn được chấm đúng, mẫu lỗi bị
    chấm sai, còn chép lại đề hoặc nộp một bước giữa trong lời giải mẫu thì không được chấm đúng."""
    problems = 0
    for pack in bank.packs:
        for case in [*pack.problems, *pack.examples]:
            problems += 1
            task, prompt = case.task.model_dump(), getattr(case, "prompt", None)  # ví dụ không có đề riêng
            assert grade(task, case.reference_answer, prompt)["assessment_status"] == "verified_correct", case.case_id
            assert is_final_form(case.task.kind, case.task.expression, case.reference_answer, prompt), case.case_id
            if case.task.kind != "word_equation":  # bài lập phương trình: phương trình chính là đáp án
                assert grade(task, case.task.expression, prompt)["assessment_status"] != "verified_correct", case.case_id
            for step in case.reference_steps[:-1]:
                assert grade(task, step, prompt)["assessment_status"] != "verified_correct", (case.case_id, step)
        by_id = {p.case_id: p for p in pack.problems}
        for error in pack.errors:
            problem = by_id[error.problem_id]
            assessment = grade(problem.task.model_dump(), error.response_steps[-1], problem.prompt)
            assert assessment["assessment_status"] == "verified_incorrect", error.error_id
    assert problems == 9 * len(bank.packs)


# ---------------------------------------------------------------- review lần 2

@pytest.mark.parametrize("answer", ["x^2 - 9x + 20", "x^2 - 9x + 20 =", "= x^2 - 9x + 20", "x^2-9x+20=0=0"])
def test_unfinished_equation_for_vieta_is_not_correct(answer):
    assert status("vieta", "from_sum_product; 9; 20", answer) != "verified_correct"


@pytest.mark.parametrize("answer", ["x^2 - 9x + 20 = 0", "x*x-9*x+20=0"])
def test_full_equation_for_vieta_is_correct(answer):
    assert status("vieta", "from_sum_product; 9; 20", answer) == "verified_correct"


N06_PROMPT = "Tính −3/4 + 5/6 − 1/3. Viết kết quả là phân số tối giản."


def test_fraction_task_needs_a_reduced_fraction_not_a_decimal():
    assert status("numeric", "-3/4+5/6-1/3", "-0.25", N06_PROMPT) == "unverified"
    assert status("numeric", "-3/4+5/6-1/3", "-1/4", N06_PROMPT) == "verified_correct"
    assert status("numeric", "1.5+2.25", "3.75", "Tính 1,5 + 2,25.") == "verified_correct"


@pytest.mark.parametrize("answer", ["x=1.5", "x=3/2", "1.5"])
def test_root_task_accepts_an_exact_decimal(answer):
    """F10 chỉ yêu cầu tìm x: 1.5 và 3/2 đều là đáp án cuối."""
    assert status("exp_log_equation", "exp; 4; x; 8", answer, "Giải phương trình 4^x = 8. Nộp dạng x=....")         == "verified_correct"


@pytest.mark.parametrize("answer, expected", [
    ("25;{sqrt(4)/4,1+sqrt(4)}", "unverified"),       # căn còn tính tiếp được
    ("25;{1/2,3}", "verified_correct"),
])
def test_rational_square_roots_must_be_evaluated(answer, expected):
    assert status("quadratic_roots", "2*x*x-7*x+3", answer) == expected


@pytest.mark.parametrize("answer, expected", [
    ("12;{(-1-sqrt(3))/2,(-1+sqrt(3))/2}", "verified_correct"),  # căn vô tỉ hợp lệ
    ("12;{(-2-sqrt(12))/4,(-2+sqrt(12))/4}", "unverified"),     # chưa đưa thừa số ra ngoài căn
    ("12;{(-2-2*sqrt(3))/4,(-2+2*sqrt(3))/4}", "unverified"),   # tử và mẫu còn chia được cho 2
    ("12;{-1/2-sqrt(3)/2,-1/2+sqrt(3)/2}", "verified_correct"),  # tách phần hữu tỉ và phần căn
    ("12;{-1/2-1*sqrt(3)/2,-1/2+1*sqrt(3)/2}", "unverified"),   # hệ số 1 thừa
    ("12;{-2/4-sqrt(3)/2,-2/4+sqrt(3)/2}", "unverified"),       # phần hữu tỉ chưa rút gọn
])
def test_irrational_roots_stay_but_must_be_simplified(answer, expected):
    assert status("quadratic_roots", "2*x*x+2*x-1", answer) == expected


@pytest.mark.parametrize("kind, expression", [
    ("log_value", "log; 1; 32"),
    ("log_value", "log; 2; -8"),
    ("numeric", "1/0"),
    ("vieta", "sum_product; x*x+x+1"),
])
def test_task_outside_the_checker_scope_is_unverified_not_an_exception(kind, expression):
    assessment = grade({"kind": kind, "expression": expression}, "5")
    assert (assessment["assessment_status"], assessment["reason_code"]) == ("unverified", "unsupported_scope")


# ---------------------------------------------------------------- review lần 4 (E06 của Hoàng)

@pytest.mark.parametrize("answer", [
    "12;{(-1-sqrt(3))/2,(-1+sqrt(3))/2}",
    "12;{(-sqrt(3)-1)/2,(sqrt(3)-1)/2}",      # đổi thứ tự hạng tử trong tử
    "12;{-1/2-sqrt(3)/2,sqrt(3)/2-1/2}",
])
def test_reduced_surd_roots_are_accepted_in_any_term_order(answer):
    assert status("quadratic_roots", "2*x*x+2*x-1", answer) == "verified_correct"


@pytest.mark.parametrize("answer", [
    "12;{(-2-2*sqrt(3))/4,(2*sqrt(3)-2)/4}",  # đổi thứ tự vẫn phải kiểm ước chung
    "12;{(-1-sqrt(3))/2,(sqrt(12)-2)/4}",     # cùng giá trị nhưng căn chưa rút gọn
])
def test_reordered_surd_roots_still_need_reducing(answer):
    assert status("quadratic_roots", "2*x*x+2*x-1", answer) == "unverified"


@pytest.mark.parametrize("answer", [
    "25;{(1+0*sqrt(3))/2,3+0*sqrt(3)}",
    "25;{1/2,3+0*sqrt(3)}",
])
def test_a_zero_surd_term_is_not_a_final_answer(answer):
    assessment = grade({"kind": "quadratic_roots", "expression": "2*x*x-7*x+3"}, answer)
    assert (assessment["assessment_status"], assessment["reason_code"]) == ("unverified", "valid_partial")


# ---------------------------------------------------------------- review lần 5

@pytest.mark.parametrize("answer", [
    "12;{-(1+sqrt(3))/2,(-1+sqrt(3))/2}",     # dấu âm đưa ra ngoài ngoặc
    "12;{-0.5-sqrt(3)/2,-0.5+sqrt(3)/2}",     # đề không bắt buộc phân số: nhận -0.5
])
def test_equivalent_finished_surd_roots_are_accepted(answer):
    assert status("quadratic_roots", "2*x*x+2*x-1", answer) == "verified_correct"


@pytest.mark.parametrize("answer", [
    "12;{-(2+2*sqrt(3))/4,(-1+sqrt(3))/2}",   # dấu ngoài ngoặc vẫn phải kiểm ước chung
    "12;{-(1+0*sqrt(3)+sqrt(3))/2,(-1+sqrt(3))/2}",
])
def test_minus_outside_brackets_keeps_the_reduction_checks(answer):
    assert status("quadratic_roots", "2*x*x+2*x-1", answer) != "verified_correct"


def test_decimal_rational_part_follows_the_prompt():
    answer = "12;{-0.5-sqrt(3)/2,-0.5+sqrt(3)/2}"
    assert status("quadratic_roots", "2*x*x+2*x-1", answer, "Nộp nghiệm ở dạng phân số tối giản.") == "unverified"
