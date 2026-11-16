"""Điều phối sinh phản hồi trong một lượt (PRD FR12-AC1, FR11-AC3):

    LLM ──(đạt)──→ gửi
     │──(lỗi sửa được, còn ngân sách)──→ LLM sinh lại kèm lý do ──(đạt)──→ gửi
     └──(vẫn không đạt / lỗi gọi model / thiếu đáp án)──→ template ──→ template an toàn ──→ câu hệ thống

Không bật LLM thì bắt đầu từ template. Câu của LLM phải qua mọi kiểm tra; template chỉ cần không lộ
đáp án (``verifier``). Mỗi lần sinh LLM là một bước riêng (``draft``), để LangGraph checkpoint nó
trước lần kiểm tra (``settle``): lượt lỗi giữa chừng chạy lại không gọi model thêm lần nữa.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.agent.decision import MAX_REGENERATIONS
from app.generation.contracts import (
    NOT_REGENERABLE, LLMSkipReason, ResponseAttempt, ResponseInput, ResponseRecord, ResponseSource, final_source,
    regenerations_used,
)
from app.generation.llm_generator import PROMPT_VERSION, LLMResponseGenerator
from app.generation.templates import SYSTEM_MESSAGE, TEMPLATE_VERSION, TemplateGenerator
from app.generation.verifier import VERIFIER_VERSION, ResponseVerifier


@dataclass(frozen=True)
class ResponseOutcome:
    attempts: tuple[ResponseAttempt, ...]
    llm_skipped_reason: LLMSkipReason | None = None

    @property
    def final_source(self) -> ResponseSource:
        return final_source(self.attempts, self.llm_skipped_reason)

    @property
    def regenerations_used(self) -> int:
        return regenerations_used(self.attempts)

    @property
    def message(self) -> str:
        last = self.attempts[-1]
        return last.message if last.accepted else SYSTEM_MESSAGE

    def record(self, turn_id: UUID, decision_id: UUID) -> ResponseRecord:
        used_llm = any(a.source == "llm" for a in self.attempts)
        return ResponseRecord(turn_id=turn_id, decision_id=decision_id, template_version=TEMPLATE_VERSION,
                              verifier_version=VERIFIER_VERSION, prompt_version=PROMPT_VERSION if used_llm else None,
                              llm_skipped_reason=self.llm_skipped_reason, attempts=list(self.attempts),
                              final_source=self.final_source, message=self.message)


class Responder:
    def __init__(self, templates: TemplateGenerator, verifier: ResponseVerifier,
                 llm: LLMResponseGenerator | None = None):
        self.templates = templates
        self.verifier = verifier
        self.llm = llm

    def _skip_reason(self, inp: ResponseInput) -> LLMSkipReason | None:
        """Có LLM nhưng không có đáp án để kiểm tra câu của nó: không gọi model."""
        if self.llm is not None and not self.verifier.has_keys(inp):
            return "answer_key_missing"
        return None

    def _uses_llm(self, inp: ResponseInput) -> bool:
        return self.llm is not None and self._skip_reason(inp) is None

    def draft(self, inp: ResponseInput, attempts: list[ResponseAttempt]) -> ResponseAttempt:
        """Lần sinh tiếp theo: LLM lần đầu, LLM sinh lại kèm lỗi của lần trước, hoặc template."""
        if self._uses_llm(inp):
            return self.llm(inp, list(attempts[-1].violations) if attempts else [])
        return self._template(inp)

    def settle(self, inp: ResponseInput, attempts: list[ResponseAttempt], *, may_regenerate: bool
               ) -> tuple[list[ResponseAttempt], ResponseOutcome | None]:
        """Kiểm tra lần sinh cuối. Trả ``None`` (kèm các lần sinh đã kiểm tra) khi cần LLM sinh lại;
        ngược lại trả kết quả cuối, sau khi đã thử template nếu cần."""
        attempts = [*attempts[:-1], self._checked(inp, attempts[-1])]
        last = attempts[-1]
        if last.accepted:
            return attempts, self._outcome(inp, attempts)
        if (last.source == "llm" and may_regenerate and regenerations_used(attempts) < MAX_REGENERATIONS
                and not set(last.violations) & NOT_REGENERABLE):
            return attempts, None
        if last.source == "llm":
            attempts.append(self._checked(inp, self._template(inp)))
        if not attempts[-1].accepted:
            safe = ResponseAttempt(source="template_safe", message=self.templates.safe(inp.decision))
            attempts.append(self._checked(inp, safe))
        return attempts, self._outcome(inp, attempts)

    def run(self, inp: ResponseInput, regenerations: int = MAX_REGENERATIONS) -> ResponseOutcome:
        """Cả chuỗi trong một lần gọi (script đánh giá, test). Graph dùng ``draft``/``settle`` riêng."""
        attempts: list[ResponseAttempt] = []
        while True:
            attempts.append(self.draft(inp, attempts))
            attempts, outcome = self.settle(inp, attempts, may_regenerate=regenerations > 0)
            if outcome is not None:
                return outcome
            regenerations -= 1

    # ------------------------------------------------------------------ nội bộ

    def _template(self, inp: ResponseInput) -> ResponseAttempt:
        return ResponseAttempt(source="template", message=self.templates(inp),
                               content_ids_used=[c.content_id for c in inp.content])

    def _checked(self, inp: ResponseInput, attempt: ResponseAttempt) -> ResponseAttempt:
        if attempt.message is None or attempt.accepted:
            return attempt
        if attempt.source == "llm":
            found = self.verifier.check_generated(inp, attempt.message, attempt.content_ids_used)
        else:
            found = self.verifier.check_template(inp, attempt.message)
        violations = list(dict.fromkeys([*attempt.violations, *found]))
        return attempt.model_copy(update={"violations": violations, "accepted": not violations})

    def _outcome(self, inp: ResponseInput, attempts: list[ResponseAttempt]) -> ResponseOutcome:
        return ResponseOutcome(tuple(attempts), self._skip_reason(inp))
