"""Nối validator của Member 1 vào Agent: chuyển kết quả validator sang AssessmentView."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import math_validator  # noqa: E402
from app.agent.graph import Services  # noqa: E402
from app.agent.rule_policy import CARELESS_FAMILIES  # noqa: E402
from app.agent.stubs import DEMO_PROBLEMS, demo_validator_task  # noqa: E402
from app.agent.validator_analyzer import MISCONCEPTION_FAMILY, ValidatorAnalyzer  # noqa: E402
from app.misconceptions import MISCONCEPTION_CATALOG  # noqa: E402

# Trong test chạy validator ngay trong tiến trình cho nhanh; runtime dùng bản có giới hạn thời gian.
analyze = ValidatorAnalyzer(demo_validator_task, validate=math_validator.validate)


def state(problem_id):
    ref = DEMO_PROBLEMS[problem_id].ref
    return SimpleNamespace(current=SimpleNamespace(problem_id=problem_id, target_skill_id=ref.target_skill_id))


def test_distribution_error_in_equation_maps_to_family_and_prerequisite_skill():
    a = analyze(state("E02-P001"), ["2x - 3 = 10", "2x = 13", "x = 6.5"])
    assert a.assessment_status == "verified_incorrect"
    assert a.first_error_step == 1
    assert a.misconception_candidate == "M_EQ_DIST_01"
    assert a.error_family == "distribution_error"
    assert a.primary_skill_id == "SK-A02-DISTRIBUTE"
    assert a.diagnosis_status == "suspected"
    assert not a.final_answer_only


def test_copied_prompt_line_keeps_learner_step_numbers():
    a = analyze(state("E02-P001"), ["2(x - 3) = 10", "", "2x - 3 = 10", "2x = 13"])
    assert a.first_error_step == 2


def test_wrong_final_answer_only_has_no_error_step():
    a = analyze(state("E02-P001"), ["x = 7"])
    assert a.assessment_status == "verified_incorrect"
    assert a.final_answer_only
    assert a.first_error_step is None
    assert a.misconception_candidate is None and a.error_family is None
    assert a.diagnosis_status == "unknown"
    assert a.primary_skill_id == "SK-E02-SOLVE"


def test_single_line_with_recognised_misconception_points_at_that_line():
    a = analyze(state("A02-P001"), ["-6y + 8"])
    assert (a.first_error_step, a.error_family, a.misconception_candidate) == (1, "sign_error", "M_DIST_02")
    assert not a.final_answer_only


def test_unrecognised_error_keeps_step_but_no_diagnosis():
    a = analyze(state("E02-P003"), ["7x - 7 = 8", "7x = 15"])
    assert a.first_error_step == 1
    assert a.error_family is None and a.misconception_candidate is None
    assert a.diagnosis_status == "unknown"


@pytest.mark.parametrize("problem_id, steps", [
    ("E02-P001", ["2x - 6 = 10", "2x = 16", "x = 8"]),
    ("A02-P001", ["-6y - 8"]),
    ("N01-P001", ["-4"]),
    ("E03-P001", ["x + 5 = 12", "x = 7"]),
])
def test_correct_work(problem_id, steps):
    a = analyze(state(problem_id), steps)
    assert a.assessment_status == "verified_correct"
    assert a.primary_skill_id == DEMO_PROBLEMS[problem_id].ref.target_skill_id


def test_unfinished_work_is_unverified_and_unclear_text_needs_clarification():
    assert analyze(state("E02-P001"), ["2x - 6 = 10"]).assessment_status == "unverified"
    assert analyze(state("E02-P001"), ["em không biết làm"]).assessment_status == "needs_clarification"
    assert analyze(state("E02-P001"), ["", "  "]).assessment_status == "needs_clarification"


def test_problem_without_validator_task_is_unverified():
    s = SimpleNamespace(current=SimpleNamespace(problem_id="X99-P001", target_skill_id="SK-X"))
    assert analyze(s, ["x = 1"]).assessment_status == "unverified"


def test_every_catalog_misconception_has_a_family():
    """Member 1 thêm misconception mới thì phải bổ sung họ lỗi, nếu không Agent mất thông tin."""
    ids = {entry["error_id"] for entries in MISCONCEPTION_CATALOG.values() for entry in entries}
    assert ids == set(MISCONCEPTION_FAMILY)
    assert "sign_error" in CARELESS_FAMILIES


def test_every_demo_problem_is_gradable_by_the_validator():
    """Agent có thể giao bất kỳ bài mẫu nào, nên đề và đáp án của mọi bài phải nằm trong phạm vi
    validator (chỉ biến x, y): nộp đáp án đúng phải được chấm là đúng, không phải "unverified"."""
    for problem_id, problem in DEMO_PROBLEMS.items():
        task = demo_validator_task(problem_id)
        assert task is not None
        math_validator.prompt_state(task)  # đề phải đọc được
        for answer in problem.answer_forms:
            assert analyze(state(problem_id), [answer]).assessment_status == "verified_correct", problem_id


def test_one_wrong_transformation_line_keeps_its_step():
    """Một dòng biến đổi sai (chưa phải đáp án x = ...) vẫn chỉ ra được bước sai."""
    a = analyze(state("E02-P001"), ["2x - 7 = 10"])
    assert a.assessment_status == "verified_incorrect"
    assert a.first_error_step == 1
    assert not a.final_answer_only


def test_copied_system_prompt_given_as_list_keeps_step_numbers():
    task = {"problem_id": "SYS-P001", "concept_id": "E02", "primary_skill_id": "SK-E02-SOLVE",
            "equations": ["x + y = 5", "x - y = 1"]}
    sys_analyze = ValidatorAnalyzer(lambda _: task, validate=math_validator.validate)
    s = SimpleNamespace(current=SimpleNamespace(problem_id="SYS-P001", target_skill_id="SK-E02-SOLVE"))
    direct = sys_analyze(s, ["x = 3; y = 2", "x = 4; y = 2"])
    copied = sys_analyze(s, ["x + y = 5; x - y = 1", "x = 3; y = 2", "x = 4; y = 2"])
    assert direct.first_error_step is not None
    assert copied.first_error_step == direct.first_error_step + 1
