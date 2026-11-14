"""Hợp đồng extraction → validator (bản nháp v1 để chốt với Member 1).

Giải thích thiết kế: docs/implementation/extraction/llm-extraction.v1.md

Nguyên tắc (PRD FR-04, FR-05):
- Extraction chỉ *tách* bước; đúng hay sai do validator quyết định.
- ``normalized`` của mỗi bước chỉ khác ``source`` ở phép chuẩn hóa ký tự tất định của grammar
  (khoảng trắng, dấu trừ Unicode, ``×``/``÷``...). Không có số hay phép toán nào được thêm, bớt, sửa.
- Không chắc thì ``needs_clarification`` và không trả bước nào: không đưa bài làm dở cho validator.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, get_args
from uuid import UUID

from pydantic import Field, model_validator

from app.agent.decision import MAX_SUBMISSION_LINES, Contract, SubmissionLine
from app.llm.types import LLMUsage

ExtractionContractVersion = Literal["extraction-contract-0.1.0"]
EXTRACTION_CONTRACT_VERSION: str = get_args(ExtractionContractVersion)[0]


class Reason(StrEnum):
    """Vì sao chưa tách được. Nhóm đầu do luật tất định phát hiện; nhóm hai do LLM báo; nhóm ba
    là chốt chặn LLM (đầu ra của LLM không trung thành với bài làm) và lỗi gọi model."""

    EMPTY = "empty"
    NO_EQUATION = "no_equation"                # không có dấu "=" nào
    NO_STEPS = "no_steps"                      # chỉ chép lại đề, chưa có bước giải
    DECIMAL_COMMA = "decimal_comma"            # "6,5": grammar yêu cầu dấu chấm, không tự đoán
    CHAINED_EQUALS = "chained_equals"          # nhiều dấu "=" trong một biểu thức
    AMBIGUOUS_FRACTION = "ambiguous_fraction"  # "1/2x": (1/2)x hay 1/(2x)?
    SYNTAX = "syntax"                          # không đúng cú pháp phương trình của grammar
    TOO_MANY_STEPS = "too_many_steps"
    STEP_TOO_LONG = "step_too_long"
    MIXED_TEXT = "mixed_text"                  # chữ lẫn công thức, không có LLM để tách

    MATH_IN_WORDS = "math_in_words"            # "hai x bằng mười sáu"
    UNSUPPORTED_NOTATION = "unsupported_notation"  # lũy thừa, căn, ẩn khác x, ":" làm phép chia...
    UNREADABLE = "unreadable"

    NOT_VERBATIM = "not_verbatim"              # LLM trả đoạn không có trong bài làm (đã sửa/bịa)
    PARTIAL_SPAN = "partial_span"              # LLM cắt bớt một biểu thức
    UNEXTRACTED_MATH = "unextracted_math"      # LLM bỏ sót một phương trình
    LLM_UNAVAILABLE = "llm_unavailable"
    LLM_INVALID_OUTPUT = "llm_invalid_output"


# Lý do LLM được phép tự báo; các lý do khác chỉ do hệ thống gán.
LLM_REASONS = frozenset({Reason.MATH_IN_WORDS, Reason.CHAINED_EQUALS, Reason.DECIMAL_COMMA,
                         Reason.UNSUPPORTED_NOTATION, Reason.UNREADABLE})
# Chốt chặn đã phải can thiệp: LLM định sửa, cắt hoặc bỏ sót bài làm của học sinh.
FIDELITY_REASONS = frozenset({Reason.NOT_VERBATIM, Reason.PARTIAL_SPAN, Reason.UNEXTRACTED_MATH})


class ExtractedStep(Contract):
    """Một phương trình học sinh đã viết.

    ``role = "restated_problem"`` là dòng chép lại đề ở đầu bài: được giữ nhưng không đánh số bước
    (FR04-AC1), nên ``index`` là None. Bước giải đánh số từ 1."""

    role: Literal["restated_problem", "step"]
    index: int | None = Field(default=None, ge=1, le=MAX_SUBMISSION_LINES)
    line: int = Field(ge=1)  # dòng của bài nộp chứa đoạn này (từ 1, đã bỏ dòng trống)
    source: Annotated[str, Field(min_length=1, max_length=400)]  # đúng đoạn học sinh viết
    normalized: SubmissionLine  # theo grammar, không khoảng trắng

    @model_validator(mode="after")
    def _numbering(self):
        if (self.role == "step") != (self.index is not None):
            raise ValueError("index is set exactly for role=step")
        return self


class ExtractionResult(Contract):
    """Đầu ra của extraction, đầu vào của validator."""

    contract_version: ExtractionContractVersion = EXTRACTION_CONTRACT_VERSION
    grammar_version: str
    status: Literal["extracted", "needs_clarification"]
    # "rules": mọi dòng đã đúng grammar, không cần LLM. "llm": LLM chọn đoạn, luật đã kiểm tra lại.
    method: Literal["rules", "llm"]
    steps: list[ExtractedStep] = Field(default_factory=list, max_length=MAX_SUBMISSION_LINES + 1)
    reasons: list[Reason] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _consistent(self):
        solving = [s for s in self.steps if s.role == "step"]
        if self.status == "extracted":
            if self.reasons or not solving:
                raise ValueError("extracted needs at least one step and no reasons")
        elif self.steps or not self.reasons:
            raise ValueError("needs_clarification carries reasons and no steps")
        if [s.index for s in solving] != list(range(1, len(solving) + 1)):
            raise ValueError("steps are numbered 1..n in order")
        if any(s.role == "restated_problem" for s in self.steps[1:]):
            raise ValueError("only the first entry can restate the problem")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("reasons must be unique")
        return self

    def graded_lines(self) -> list[str]:
        """Các bước giải ở dạng chuẩn hóa, đúng thứ tự: phần đưa cho validator chấm."""
        return [s.normalized for s in self.steps if s.role == "step"]


class ExtractionRecord(Contract):
    """Một dòng trong extraction log của phiên: lượt nào, tách bằng gì, tốn bao nhiêu."""

    turn_id: UUID
    extractor_version: str
    prompt_version: str | None = None  # None khi không gọi LLM
    result: ExtractionResult
    usage: LLMUsage | None = None      # None khi không gọi LLM
    # Đúng chuỗi model trả về (hoặc lời từ chối), trước chốt chặn: để phân biệt model cắt sai với
    # chốt chặn từ chối nhầm khi đọc lại (NFR-04). None khi không gọi LLM hoặc lần gọi lỗi.
    llm_output: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def _llm_trace(self):
        if (self.usage is None) != (self.prompt_version is None):
            raise ValueError("usage and prompt_version are recorded together, only when the LLM was called")
        if self.llm_output is not None and self.usage is None:
            raise ValueError("llm_output is only recorded when the LLM was called")
        return self


EXPORTED_MODELS = (ExtractionResult, ExtractionRecord)
