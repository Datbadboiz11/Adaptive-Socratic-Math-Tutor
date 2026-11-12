"""Internal pilot assessment contracts; separate from persistent MVP sessions."""
from typing import Annotated, Literal

from pydantic import Field

from app.contracts import Assessment, Contract, Identifier
from app.curriculum import MathTask


class PilotSubmission(Contract):
    # Explicit intent prevents an isolated wrong answer becoming a diagnosis.
    submission_kind: Literal['final_answer', 'steps']
    steps: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(min_length=1, max_length=12)


class PilotProblem(Contract):
    problem_id: Identifier
    concept_id: Identifier
    primary_skill_id: Identifier
    content_version: str
    prompt: str
    task: MathTask
    mode: Literal['internal_authoring_preview'] = 'internal_authoring_preview'
    review_status: str


class StepCheck(Contract):
    step: int = Field(ge=1)
    status: Literal['equivalent', 'incorrect', 'unverified', 'not_assessed']


class PilotAnalysis(Contract):
    problem_id: Identifier
    concept_id: Identifier
    content_version: str
    submission_kind: Literal['final_answer', 'steps']
    assessment: Assessment
    step_checks: list[StepCheck]
    completed: bool
    diagnostic_question: str | None = None
    diagnostic_source: Literal['authored_pattern', 'none'] = 'none'
    updates_student_model: Literal[False] = False
    mode: Literal['internal_authoring_preview'] = 'internal_authoring_preview'
    analysis_version: str = 'pilot-analyzer-1.0.0'
    limitations: list[str]
