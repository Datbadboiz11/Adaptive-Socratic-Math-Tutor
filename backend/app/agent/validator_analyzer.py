"""Analyzer thật: chấm bài bằng validator SymPy + danh mục misconception của Member 1.

Thay ``StubAnalyzer``. Lớp này chỉ chuyển kết quả của ``app.math_validator`` sang ``AssessmentView``
mà Agent dùng, và xử lý các chỗ hai bên chưa thống nhất contract:

- ``error_family``: validator trả mã misconception (``M_DIST_01``) ở cả ``error_family`` lẫn
  ``misconception_candidate``. Agent cần họ lỗi (``distribution_error``, ``sign_error``...) để chọn
  cách hỗ trợ, nên tra bảng ``MISCONCEPTION_FAMILY`` bên dưới. Bảng này là đề xuất của Member 3,
  chờ Member 1 xác nhận.
- ``diagnosis_status="unverified"`` (validator) → ``"unknown"`` (Agent);
  ``misconception_candidate="unknown"`` → None.
- Bài chỉ ghi đáp án cuối và sai (validator báo ``reason_code="wrong_final_answer"`` kèm
  ``first_error_step=1``): Agent ghi ``final_answer_only=True`` và để trống bước sai, vì học sinh chưa
  viết bước nào để chỉ ra. Một dòng biến đổi sai (chưa phải đáp án) vẫn giữ số bước.
- Validator bỏ qua dòng đầu nếu đó là chép lại đề, nên số bước nó trả về lệch một so với bài làm.
  Agent đánh số theo các dòng không trống học sinh đã nộp, nên cộng bù lại.
"""
from __future__ import annotations

from collections.abc import Callable
import re
from uuid import UUID, uuid4

from app import math_validator
from app.agent.decision import AssessmentView, StudentState

ValidateFn = Callable[[dict, list[str]], dict]

# Mã misconception (Member 1) → (họ lỗi, skill bị ảnh hưởng). Skill None: dùng skill của bài.
# Họ lỗi "sign_error" thuộc nhóm lỗi sơ suất của Rule-policy (CARELESS_FAMILIES): khi skill đã
# thành thạo, lỗi dấu được xem là sơ suất thay vì thiếu kiến thức.
MISCONCEPTION_FAMILY: dict[str, tuple[str, str | None]] = {
    "M_SUB_01": ("sign_error", "SK-A01-EVALUATE"),
    "M_SUB_02": ("exponent_error", "SK-A01-EVALUATE"),
    "M_DIST_01": ("distribution_error", "SK-A02-DISTRIBUTE"),
    "M_DIST_02": ("sign_error", "SK-A02-DISTRIBUTE"),
    "M_LIKE_01": ("combine_terms_error", "SK-A03-COLLECT"),
    "M_LIKE_02": ("sign_error", "SK-A03-COLLECT"),
    "M_POLY_01": ("expansion_error", "SK-A04-PRIMARY"),
    "M_POLY_02": ("sign_error", "SK-A04-PRIMARY"),
    "M_SQUARE_01": ("identity_error", "SK-A05-PRIMARY"),
    "M_SQUARE_02": ("identity_error", "SK-A05-PRIMARY"),
    "M_DIFFSQ_01": ("sign_error", "SK-A06-PRIMARY"),
    "M_DIFFSQ_02": ("identity_error", "SK-A06-PRIMARY"),
    "M_FACTOR_01": ("factoring_error", "SK-A07-PRIMARY"),
    "M_FACTOR_02": ("factoring_error", "SK-A07-PRIMARY"),
    "M_GROUP_01": ("factoring_error", "SK-A08-PRIMARY"),
    "M_GROUP_02": ("sign_error", "SK-A08-PRIMARY"),
    "M_EQ_01": ("inverse_operation_error", None),
    "M_EQ_02": ("sign_error", None),
    "M_INV_01": ("inverse_operation_error", None),
    "M_SIGN_01": ("sign_error", None),
    # Lỗi phân phối trong lúc giải phương trình: gốc ở kỹ năng phân phối (A02).
    "M_EQ_DIST_01": ("distribution_error", "SK-A02-DISTRIBUTE"),
    "M_EQ_DIST_02": ("sign_error", "SK-A02-DISTRIBUTE"),
    "M_MODEL_01": ("modeling_error", None),
    "M_MODEL_02": ("modeling_error", None),
    "M_ZERO_01": ("root_loss_error", None),
    "M_ZERO_02": ("zero_product_error", None),
    "M_DOMAIN_01": ("condition_error", None),
    "M_DOMAIN_02": ("condition_error", None),
    "M_QUAD_01": ("root_loss_error", None),
    "M_QUAD_02": ("sign_error", None),
}


def _repeats_prompt(line: str, task: dict) -> bool:
    """Đúng phép so của validator (``math_validator.validate``) khi bỏ dòng chép lại đề: cùng cách
    chọn trường đề và cùng ``split_rows``, nên nhận cả đề dạng chuỗi lẫn danh sách phương trình."""
    prompt = (task.get("expression") if "expression" in task
              else task.get("equations", task.get("system", task.get("equation"))))
    try:
        squash = lambda text: [re.sub(r"\s", "", row) for row in math_validator.split_rows(text)]
        return squash(math_validator.normalize(line)) == squash(prompt)
    except Exception:
        return False


class ValidatorAnalyzer:
    """``task_for(problem_id)`` trả đề ở dạng validator đọc được (None nếu không có).
    ``validate`` mặc định chạy validator trong tiến trình con có giới hạn thời gian."""

    def __init__(self, task_for: Callable[[str], dict | None],
                 validate: ValidateFn = math_validator.validate_bounded,
                 new_id: Callable[[], UUID] = uuid4):
        self.task_for = task_for
        self.validate = validate
        self.new_id = new_id

    def __call__(self, state: StudentState, steps: list[str]) -> AssessmentView:
        lines = [line for line in steps if line.strip()]
        task = self.task_for(state.current.problem_id)
        if task is None:
            return AssessmentView(assessment_id=self.new_id(), assessment_status="unverified")
        raw = self.validate(task, lines).get("assessment", {})
        return self._view(raw, lines, task, state)

    def _view(self, raw: dict, lines: list[str], task: dict, state: StudentState) -> AssessmentView:
        status = raw.get("assessment_status", "unverified")
        if status not in {"verified_correct", "verified_incorrect", "needs_clarification"}:
            status = "unverified"
        if status != "verified_incorrect":
            skill = raw.get("primary_skill_id") if status == "verified_correct" else None
            return AssessmentView(assessment_id=self.new_id(), assessment_status=status,
                                  primary_skill_id=skill,
                                  unfinished=status == "unverified" and raw.get("reason_code") == "valid_partial")

        offset = 1 if lines and _repeats_prompt(lines[0], task) else 0
        candidate = raw.get("misconception_candidate")
        candidate = None if candidate in (None, "", "unknown") else candidate
        family, skill = MISCONCEPTION_FAMILY.get(candidate, (None, None)) if candidate else (None, None)
        skill = skill or raw.get("primary_skill_id") or state.current.target_skill_id
        step = raw.get("first_error_step")
        # Chỉ validator biết dòng duy nhất là đáp án cuối (x = ...) hay là một bước biến đổi.
        final_only = raw.get("reason_code") == "wrong_final_answer"
        return AssessmentView(
            assessment_id=self.new_id(), assessment_status="verified_incorrect",
            first_error_step=None if final_only or step is None else step + offset,
            primary_skill_id=skill, error_family=family, misconception_candidate=candidate,
            diagnosis_status="suspected" if candidate else "unknown", final_answer_only=final_only)
