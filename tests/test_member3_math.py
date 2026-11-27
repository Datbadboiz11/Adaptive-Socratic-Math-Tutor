"""Dạng kiểm toán bổ sung của Member 3 (backend/app/member3_math.py)."""
from fractions import Fraction as F
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import math_validator  # noqa: E402
from app.assessment_modes import ASSESSMENT_MODE, TASK_KINDS  # noqa: E402
from app.authoring_extended_math import TASK_CHECKS  # noqa: E402
from app.member3_math import MEMBER3_CHECKS, MEMBER3_TASK_KINDS  # noqa: E402


def same(kind, expression, response):
    expected, answer = MEMBER3_CHECKS[kind]
    return expected(expression) == answer(expression, response)


# Câu trả lời đúng, kể cả cách viết tự nhiên của học sinh.
CORRECT = [
    ("linear_inequality", "2*x-7<5", "x<6"),
    ("linear_inequality", "-3*x+4<19", "x > -5"),
    ("linear_inequality", "-4*x-6>=10", "x ≤ −4"),
    ("linear_inequality", "-4*x-6>=10", "-4>=x"),
    ("log_value", "log; 3; 1/27", "-3"),
    ("log_value", "log; 4; 8", "3/2"),
    ("log_value", "sum; 6; 4; 9", "2"),
    ("log_value", "difference; 3; 54; 2", "3"),
    ("exp_log_equation", "exp; 2; x+3; 32", "x = 2"),
    ("exp_log_equation", "exp; 9; x+1; 27", "x=1/2"),
    ("exp_log_equation", "log; 2; x+5; -1", "x=-9/2"),
    ("vieta", "sum_product; 2*x*x+5*x-3", "S=-5/2; P=-3/2"),
    ("vieta", "sum_product; 2*x*x+5*x-3", "P = -3/2; S = -5/2"),
    ("vieta", "other_root; 3*x*x+7*x-6; -3", "x=2/3"),
    ("vieta", "from_sum_product; -3; -10", "x^2 + 3x - 10 = 0"),
    ("vieta", "from_sum_product; -3; -10", "2x² + 6x − 20 = 0"),
    ("quadratic_monotonic", "-x*x+4*x+1", "đồng biến trên (-inf; 2), nghịch biến trên (2; +inf)"),
    ("quadratic_monotonic", "-x*x+4*x+1", "Nghịch biến trên (2; +∞) và đồng biến trên (−∞; 2)"),
    ("quadratic_monotonic", "2*x*x-6*x+1", "nghịch biến trên (-∞; 3/2], đồng biến trên [3/2; +∞)"),
    ("slope_intercept", "linear; 5-x/2", "a=-1/2; b=5"),
    ("slope_intercept", "point; -2; -3; 4", "a=-2; b=-2"),
    ("slope_intercept", "points; -2,7; 2,-1", "b=3; a=-2"),
    ("special_factoring", "9*x*x-16", "(3x-4)(3x+4)"),
    ("special_factoring", "4*x*x-12*x+9", "(2x − 3)²"),
    ("special_factoring", "2*x*x+6*x-x-3", "(2*x-1)*(x+3)"),
    ("product_equation", "(2*x-3)*(3*x+4)", "{-4/3; 3/2}"),
    ("product_equation", "x*(x-4)=3*(x-4)", "{4, 3}"),
]

# Câu trả lời đọc được nhưng sai: đúng các mẫu lỗi đã soạn.
WRONG = [
    ("linear_inequality", "-3*x+4<19", "x<-5"),          # quên đổi chiều
    ("log_value", "log; 2; 64", "32"),
    ("exp_log_equation", "log; 3; 2*x-1; 2", "x=7/2"),   # 2x − 1 = 3 · 2
    ("vieta", "sum_product; x*x-9*x+14", "S=-9; P=14"),
    ("vieta", "from_sum_product; 9; 20", "x*x+9*x+20=0"),
    ("quadratic_monotonic", "x*x-6*x+5", "đồng biến trên (-inf; 3), nghịch biến trên (3; +inf)"),
    ("quadratic_monotonic", "2*x*x-6*x+1", "nghịch biến trên (-inf; 3), đồng biến trên (3; +inf)"),
    ("slope_intercept", "linear; 7-2*x", "a=7; b=-2"),
    ("special_factoring", "x*x-49", "(x-7)*(x-7)"),
    ("product_equation", "x*(x-4)=3*(x-4)", "{3}"),      # chia hai vế cho x − 4
]

# Không đọc được hoặc không đúng hình thức yêu cầu: ném ValueError.
UNREADABLE = [
    ("linear_inequality", "2*x-7<5", "6"),
    ("linear_inequality", "2*x-7<5", "x<6<7"),
    ("log_value", "log; 2; 64", "log 64"),
    ("vieta", "sum_product; x*x-9*x+14", "9; 14"),
    ("vieta", "sum_product; x*x-9*x+14", "S=9; S=14"),
    ("quadratic_monotonic", "x*x-6*x+5", "đồng biến trên (3; +inf)"),
    ("quadratic_monotonic", "x*x-6*x+5", "đồng biến trên (3; +inf), đồng biến trên (-inf; 3)"),
    ("slope_intercept", "linear; 7-2*x", "-2; 7"),
    ("special_factoring", "x*x-49", "x*x-49"),            # chưa phân tích
    ("special_factoring", "x*x-49", "1*(x*x-49)"),
    ("product_equation", "(x-6)*(x+4)", "6; -4"),
]

# Đề nằm ngoài phạm vi: checker từ chối thay vì cho một đáp án sai.
OUT_OF_SCOPE = [
    ("linear_inequality", "2*x-7<2*x+5"),                # không còn ẩn
    ("linear_inequality", "x*x<4"),
    ("log_value", "log; 1; 5"),
    ("log_value", "log; 2; -8"),
    ("log_value", "log; 2; 3"),                          # không hữu tỉ
    ("exp_log_equation", "exp; 2; x; -4"),
    ("exp_log_equation", "log; 1; x; 2"),
    ("vieta", "sum_product; x*x+x+1"),                   # vô nghiệm thực
    ("vieta", "other_root; x*x-5*x+6; 4"),               # 4 không là nghiệm
    ("vieta", "from_sum_product; 1; 5"),
    ("slope_intercept", "linear; 5"),
    ("slope_intercept", "points; 1,2; 1,5"),
    ("special_factoring", "x*x-2"),                      # nghiệm vô tỉ
    ("product_equation", "x*x+1"),
]


@pytest.mark.parametrize("kind, expression, response", CORRECT)
def test_correct_answers_are_accepted(kind, expression, response):
    assert same(kind, expression, response)


@pytest.mark.parametrize("kind, expression, response", WRONG)
def test_wrong_answers_are_read_but_rejected(kind, expression, response):
    assert not same(kind, expression, response)


@pytest.mark.parametrize("kind, expression, response", UNREADABLE)
def test_answers_in_the_wrong_form_are_not_read(kind, expression, response):
    with pytest.raises(ValueError):
        MEMBER3_CHECKS[kind][1](expression, response)


@pytest.mark.parametrize("kind, expression", OUT_OF_SCOPE)
def test_tasks_outside_the_scope_are_refused(kind, expression):
    with pytest.raises(ValueError):
        MEMBER3_CHECKS[kind][0](expression)


def test_exact_values():
    assert MEMBER3_CHECKS["linear_inequality"][0]("7-2*x<=3*x-8") == (">=", F(3))
    assert MEMBER3_CHECKS["exp_log_equation"][0]("exp; 8; x; 16") == F(4, 3)
    assert MEMBER3_CHECKS["quadratic_monotonic"][0]("-4*x*x+2*x+3") == frozenset(
        {("increasing", "left", F(1, 4)), ("decreasing", "right", F(1, 4))})


def test_new_kinds_are_added_without_replacing_existing_checks():
    assert MEMBER3_TASK_KINDS <= TASK_KINDS
    for kind, check in MEMBER3_CHECKS.items():
        assert TASK_CHECKS[kind] is check
    assert {"factored_polynomial", "quadratic_roots", "exponent_numeric"} <= set(TASK_CHECKS)
    assert not MEMBER3_TASK_KINDS & {"factored_polynomial", "quadratic_roots", "exponent_numeric", "quadratic_axis"}


@pytest.mark.parametrize("kind, expression, answer, status", [
    ("linear_inequality", "-3*x+4<19", "x > −5", "verified_correct"),
    ("linear_inequality", "-3*x+4<19", "x < −5", "verified_incorrect"),
    ("special_factoring", "x*x-49", "(x − 7)(x + 7)", "verified_correct"),
    ("product_equation", "x*(x-4)=3*(x-4)", "{3}", "verified_incorrect"),
    ("quadratic_monotonic", "x*x-6*x+5", "đồng biến trên (3; +∞)", "needs_clarification"),
])
def test_runtime_validator_grades_member3_tasks(kind, expression, answer, status):
    """Bài đã duyệt dùng chế độ chấm đáp án cuối của Member 2; dạng mới đi qua cùng đường đó."""
    problem = {"problem_id": "M3-T", "concept_id": "E10", "primary_skill_id": "SK-M3",
               "assessment_mode": ASSESSMENT_MODE, "review": {"status": "human_approved"},
               "task": {"kind": kind, "expression": expression}}
    assert math_validator.validate(problem, ["nháp", answer])["assessment"]["assessment_status"] == status


def test_public_problem_contract_confirmed_by_the_team_is_unchanged():
    """Hợp đồng bài công khai v0.3.0 đã được cả nhóm xác nhận: dạng mới chỉ dùng cho nháp và review."""
    from pydantic import ValidationError
    from app.curriculum import DraftMathTask
    from app.member2_problem_contract import PublicTask

    assert DraftMathTask(kind="vieta", expression="sum_product; x*x-9*x+14").kind == "vieta"
    with pytest.raises(ValidationError):
        PublicTask(kind="vieta", expression="sum_product; x*x-9*x+14")
