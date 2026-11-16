"""Hợp đồng của bước sinh phản hồi: đầu vào cho generator và bản ghi response log.

Giải thích thiết kế: docs/implementation/generation/response-generation.v1.md

Nguyên tắc (PRD FR-12, FR09-AC2; plan §8.5, §18.2):
- Generator chỉ nhận phần được phép: quyết định đã qua gate, đề bài công khai, nội dung đã truy
  xuất mà quyết định trích, bài làm và lời nhắn của học sinh. Đáp án nằm riêng ở verifier.
- Mỗi lần sinh đều được ghi lại kèm lỗi mà verifier tìm thấy, kể cả lần bị thay bằng template.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.agent.decision import (
    MAX_REGENERATIONS, AssessmentView, Contract, DecisionProposal, Identifier, StudentState,
)
from app.agent.tools import RetrievedContent, TurnContext
from app.llm.types import LLMUsage

# Nguồn của câu cuối cùng gửi học sinh: template là đường chính khi không bật LLM; template_fallback
# là template thay cho câu không đạt; system là câu dừng cố định khi cả template cũng không đạt.
ResponseSource = Literal["template", "template_fallback", "llm", "system"]
# Có generator LLM nhưng không dùng ở lượt này (thiếu đáp án để kiểm tra câu của nó).
LLMSkipReason = Literal["answer_key_missing"]
MAX_MESSAGE_LENGTH = 2000  # giới hạn của TutorReply.message
MAX_LLM_OUTPUT_CHARS = 8000  # phần đầu ra thô của model được giữ trong log
MAX_ATTEMPTS = 1 + MAX_REGENERATIONS + 2  # LLM (kể cả sinh lại), template đầy đủ, template an toàn


class Check(StrEnum):
    """Lỗi verifier tìm thấy ở một lần sinh, hoặc lý do lần sinh LLM không cho ra câu nào."""

    ANSWER_LEAK = "answer_leak"                # có đáp án cuối (hoặc giá trị tương đương) của bài cần giữ
    ANSWER_KEY_MISSING = "answer_key_missing"  # không có đáp án để kiểm tra, nên không dùng LLM
    MATH_UNVERIFIED = "math_unverified"        # có toán mà verifier không xác minh được là không lộ đáp án
    UNSOURCED_EQUATION = "unsourced_equation"  # đẳng thức không có trong nguồn được đưa cho generator
    UNSOURCED_EXPRESSION = "unsourced_expression"  # biểu thức có biến không có trong nguồn (bước LLM tự làm)
    UNVERIFIED_AFFIRMATION = "unverified_affirmation"  # nói bài/bước là đúng khi chưa được xác minh đúng
    HINT_LEVEL_EXCEEDED = "hint_level_exceeded"  # chỉ cách làm quá mức hint đã duyệt
    MISSING_QUESTION = "missing_question"      # action là câu hỏi (diagnose, conceptual_question) mà không hỏi
    UNKNOWN_CONTENT = "unknown_content"        # trích content ID mà quyết định không có
    MISSING_CONTENT = "missing_content"        # action cần nội dung đã duyệt nhưng câu không dùng
    TOO_MANY_QUESTIONS = "too_many_questions"
    TOO_LONG = "too_long"
    REPEATED_MESSAGE = "repeated_message"      # trùng nguyên văn một câu vừa gửi (FR13-AC2)
    LLM_UNAVAILABLE = "llm_unavailable"        # timeout, lỗi mạng hoặc provider
    LLM_INVALID_OUTPUT = "llm_invalid_output"  # từ chối, bị cắt hoặc sai schema


# Sinh lại không sửa được các lỗi này: chuyển thẳng sang template (PRD FR11-AC3).
NOT_REGENERABLE = frozenset({Check.ANSWER_KEY_MISSING, Check.LLM_UNAVAILABLE, Check.LLM_INVALID_OUTPUT})
GENERATION_FAILURES = frozenset({Check.LLM_UNAVAILABLE, Check.LLM_INVALID_OUTPUT})


@dataclass(frozen=True)
class ResponseInput:
    """Mọi thứ generator (LLM hoặc template) được thấy trong một lượt. Không có đáp án hay lời giải.

    ``content`` chỉ gồm nội dung mà quyết định trích (``final.content_ids``); gate đã kiểm tra
    mức tiết lộ của chúng không vượt ``hint_level``. ``previous_messages`` là vài câu gia sư vừa gửi,
    để không lặp nguyên văn. ``target_skill_title`` là tên chủ đề của skill mà quyết định nhắm tới
    (tên concept trong registry), để câu hỏi về một skill nền nói được nó hỏi về phần nào."""

    decision: DecisionProposal
    problem_id: str
    problem_prompt: str | None
    new_problem_prompt: str | None
    content: tuple[RetrievedContent, ...]
    assessment: AssessmentView | None
    submission: tuple[str, ...]
    student_message: str | None
    previous_messages: tuple[str, ...] = ()
    target_skill_title: str | None = None

    @property
    def solved_current(self) -> bool:
        """Học sinh đã tự giải đúng bài đang làm (được xác minh): xác nhận đáp án đó không là tiết lộ."""
        return self.assessment is not None and self.assessment.assessment_status == "verified_correct"


def response_input(state: StudentState, decision: DecisionProposal, ctx: TurnContext,
                   problem_prompt: Callable[[str], str | None],
                   previous_messages: tuple[str, ...] = (), *,
                   skill_title: Callable[[str], str | None] | None = None) -> ResponseInput:
    content = tuple(c for cid in decision.content_ids if (c := ctx.content(cid)) is not None)
    return ResponseInput(
        decision=decision, problem_id=state.current.problem_id,
        problem_prompt=problem_prompt(state.current.problem_id),
        new_problem_prompt=problem_prompt(decision.problem_id) if decision.problem_id else None,
        content=content, assessment=state.latest_assessment, submission=tuple(state.latest_submission),
        student_message=state.latest_student_message, previous_messages=tuple(previous_messages),
        target_skill_title=skill_title(decision.target_skill_id) if skill_title and decision.target_skill_id else None)


class ResponseAttempt(Contract):
    """Một lần sinh. ``source``: ``llm``; ``template`` (template đầy đủ, có chèn nội dung và đề bài);
    ``template_safe`` (template không chèn gì, câu dự phòng cuối cùng)."""

    source: Literal["llm", "template", "template_safe"]
    message: str | None = Field(default=None, min_length=1, max_length=MAX_MESSAGE_LENGTH)
    content_ids_used: list[Identifier] = Field(default_factory=list, max_length=5)
    violations: list[Check] = Field(default_factory=list)
    accepted: bool = False
    usage: LLMUsage | None = None
    # Đúng chuỗi model trả về (NFR-04): đọc lại được vì sao một câu bị chặn.
    llm_output: str | None = Field(default=None, max_length=MAX_LLM_OUTPUT_CHARS)

    @model_validator(mode="after")
    def _consistent(self):
        if self.source != "llm" and (self.usage or self.llm_output):
            raise ValueError("usage and llm_output belong to LLM attempts")
        if self.llm_output is not None and self.usage is None:
            raise ValueError("llm_output is only recorded when the LLM was called")
        failed = bool(set(self.violations) & GENERATION_FAILURES)
        if failed and (self.source != "llm" or self.message is not None):
            raise ValueError("generation failures are LLM attempts without a message")
        if self.message is None and not failed:
            raise ValueError("an attempt without a message must say why")
        if self.accepted and (self.message is None or self.violations):
            raise ValueError("an accepted attempt has a message and no violations")
        if len(set(self.violations)) != len(self.violations):
            raise ValueError("violations must be unique")
        return self


class ResponseRecord(Contract):
    """Một dòng trong response log của phiên: câu đã gửi, nguồn, và mọi lần sinh trước đó."""

    turn_id: UUID
    decision_id: UUID
    template_version: str
    verifier_version: str
    prompt_version: str | None = None  # chỉ có khi đã gọi LLM
    llm_skipped_reason: LLMSkipReason | None = None  # có thì lượt này đi đường template
    attempts: list[ResponseAttempt] = Field(min_length=1, max_length=MAX_ATTEMPTS)
    final_source: ResponseSource
    message: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)]

    @property
    def regenerations_used(self) -> int:
        return regenerations_used(self.attempts)

    @model_validator(mode="after")
    def _consistent(self):
        llm = [a for a in self.attempts if a.source == "llm"]
        if len(llm) > 1 + MAX_REGENERATIONS:
            raise ValueError(f"at most {MAX_REGENERATIONS} regeneration(s) per turn")
        if (self.prompt_version is None) == bool(llm):
            raise ValueError("prompt_version is recorded exactly when the LLM was called")
        if self.llm_skipped_reason is not None and llm:
            raise ValueError("a skipped LLM has no attempts")
        accepted = [i for i, a in enumerate(self.attempts) if a.accepted]
        if accepted and accepted != [len(self.attempts) - 1]:
            raise ValueError("only the last attempt can be accepted")
        if not accepted:
            if self.final_source != "system":
                raise ValueError("without an accepted attempt the reply is the system message")
            return self
        last = self.attempts[-1]
        if self.message != last.message:
            raise ValueError("message must be the accepted attempt")
        if self.final_source != final_source(self.attempts, self.llm_skipped_reason):
            raise ValueError("final_source does not match the attempts")
        return self


def regenerations_used(attempts: Sequence[ResponseAttempt]) -> int:
    """Số lần LLM sinh lại; thay bằng template là fallback, không tính (FR12-AC1)."""
    return max(0, sum(a.source == "llm" for a in attempts) - 1)


def final_source(attempts: Sequence[ResponseAttempt], llm_skipped_reason: LLMSkipReason | None) -> ResponseSource:
    """Nguồn của câu gửi đi, suy từ các lần sinh (lần cuối là lần được nhận, nếu có)."""
    last = attempts[-1]
    if not last.accepted:
        return "system"
    if last.source == "llm":
        return "llm"
    first_choice = len(attempts) == 1 and last.source == "template" and llm_skipped_reason is None
    return "template" if first_choice else "template_fallback"


EXPORTED_MODELS = (ResponseRecord,)
