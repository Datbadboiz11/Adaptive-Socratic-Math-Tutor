"""Version 1 contracts. Public responses explicitly exclude private references."""
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AssessmentStatus(StrEnum):
    CORRECT = "verified_correct"
    INCORRECT = "verified_incorrect"
    UNVERIFIED = "unverified"
    CLARIFY = "needs_clarification"


class ProblemPublic(Contract):
    problem_id: Identifier
    content_version: str
    concept_id: Identifier
    primary_skill_id: Identifier
    family_id: Identifier
    prompt: str
    equation: str
    domain: Literal["real_numbers"] = "real_numbers"
    difficulty: Literal["introductory", "standard"]


class Review(Contract):
    status: Literal["draft", "machine_checked", "human_approved"]
    author: str
    source: str
    human_reviewer: str | None = None
    reviewed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def approval_has_provenance(self):
        if self.status == "human_approved" and (
            not self.human_reviewer or not self.reviewed_at
        ):
            raise ValueError("Human approval requires reviewer and timestamp")
        return self


class ReferenceMethod(Contract):
    name: str
    steps: list[str] = Field(min_length=1, max_length=12)


class CommonError(Contract):
    error_id: Identifier
    steps: list[str] = Field(min_length=1, max_length=12)
    first_error_step: int = Field(ge=1)
    explanation: str
    hypothesis: str
    diagnosis_status: Literal["suspected"] = "suspected"


class WorkedExample(Contract):
    equation: str
    answer: str
    steps: list[str] = Field(min_length=1)


class ProblemPrivate(ProblemPublic):
    source_group: Identifier
    target_scope: Literal["task_solution"]
    prerequisite_skill_ids: list[Identifier]
    reference_answer: str
    reference_methods: list[ReferenceMethod] = Field(min_length=2)
    common_errors: list[CommonError] = Field(min_length=1)
    hint_ladder: list[str] = Field(min_length=3, max_length=3)
    worked_example: WorkedExample
    split: Literal["authoring_dev"]
    review: Review

    def to_public(self) -> ProblemPublic:
        return ProblemPublic.model_validate(
            self.model_dump(include=set(ProblemPublic.model_fields))
        )


class ContentBank(Contract):
    schema_version: Literal["1.0.0"]
    content_version: str
    topic_id: Identifier
    title: str
    problems: list[ProblemPrivate] = Field(min_length=6)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [p.problem_id for p in self.problems]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate problem IDs")
        if any(p.content_version != self.content_version for p in self.problems):
            raise ValueError("Mixed content versions")
        return self


class CreateSession(Contract):
    request_id: UUID
    demo_profile_id: Identifier
    topic_id: Identifier


class SessionPublic(Contract):
    session_id: UUID
    student_id: Identifier
    status: Literal["active", "paused", "completed"]
    state_version: int = Field(ge=1)
    current_opportunity_id: UUID
    problem: ProblemPublic
    draft: str = Field(default="", max_length=2000)
    hint_level: int = Field(default=0, ge=0, le=3)
    created_at: AwareDatetime


class DraftRequest(Contract):
    request_id: UUID
    expected_state_version: int = Field(ge=1)
    draft: str = Field(max_length=2000)


class TurnRequest(Contract):
    request_id: UUID
    opportunity_id: UUID
    expected_state_version: int = Field(ge=1)
    action: Literal["submit", "request_hint"]
    steps: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
        default_factory=list, max_length=12
    )

    @model_validator(mode="after")
    def action_payload(self):
        if self.action == "submit" and not self.steps:
            raise ValueError("Submit requires at least one nonempty step")
        if self.action == "request_hint" and self.steps:
            raise ValueError("A hint request must not submit an answer")
        return self


class Assessment(Contract):
    assessment_id: UUID
    assessment_status: AssessmentStatus
    first_error_step: int | None = Field(default=None, ge=1)
    primary_skill_id: Identifier | None = None
    error_family: str | None = None
    misconception_candidate: str | None = None
    diagnosis_status: Literal["suspected", "supported", "unknown"] = "unknown"
    reason_code: Literal[
        "valid_solution", "invalid_transformation", "wrong_final_answer",
        "valid_partial", "ambiguous_input", "unsupported_scope", "cannot_verify"
    ]
    evidence: list[str] = Field(default_factory=list)
    verification_method: Literal["symbolic_and_rule", "reference", "none"]
    validator_version: str

    @model_validator(mode="after")
    def error_requires_verified_incorrect(self):
        if self.first_error_step is not None and self.assessment_status != AssessmentStatus.INCORRECT:
            raise ValueError("Do not invent a wrong step for unverified/correct input")
        if self.diagnosis_status == "suspected" and not self.misconception_candidate:
            raise ValueError("Suspected diagnosis requires a candidate")
        return self


class Opportunity(Contract):
    opportunity_id: UUID
    session_id: UUID
    student_id: Identifier
    problem_id: Identifier
    content_version: str
    target_skill_id: Identifier
    target_scope: Literal["task_solution"]
    relation: Literal["initial", "near_practice", "cross_family", "repeat"]
    related_problem_id: Identifier | None = None
    assistance_level: int = Field(ge=0, le=3)
    has_standard_observation: bool = False
    eligibility_protocol_version: Literal["g2-v1"]


class Eligibility(Contract):
    eligible: bool
    reason: Literal[
        "first_independent_verified", "already_observed", "assisted",
        "not_verified", "not_target_evidence", "near_practice", "repeat"
    ]

    @model_validator(mode="after")
    def consistent_reason(self):
        if self.eligible != (self.reason == "first_independent_verified"):
            raise ValueError("Eligibility and reason disagree")
        return self


class Observation(Contract):
    observation_id: UUID
    opportunity_id: UUID
    student_id: Identifier
    skill_id: Identifier
    assessment_id: UUID
    correct: bool
    prediction_before: Probability
    mastery_before: Probability
    mastery_after: Probability
    parameter_version: str
    eligibility_protocol_version: Literal["g2-v1"]
    created_at: AwareDatetime


class TutorResponse(Contract):
    action: Literal["ask", "hint", "different_example", "confirm", "clarify", "offer_pause"]
    message: str = Field(min_length=1, max_length=2000)
    target_skill_id: Identifier | None
    hint_level: int = Field(ge=0, le=3)
    evidence_ids: list[UUID]
    content_ids: list[Identifier]
    next_actions: list[Literal["submit", "request_hint", "next_problem", "pause", "finish"]]
    response_source: Literal["openai", "reviewed_fallback"]
    policy_version: str


class SessionReport(Contract):
    session_id: UUID
    independent_correct: int = Field(ge=0)
    assisted_correct: int = Field(ge=0)
    valid_observations: int = Field(ge=0)
    unverified_submissions: int = Field(ge=0)
    completed_at: AwareDatetime
    limitations: list[str]


class ErrorResponse(Contract):
    code: Literal[
        "invalid_input", "not_found", "state_conflict", "idempotency_conflict",
        "content_not_ready", "database_unavailable", "model_unavailable"
    ]
    message: str
    request_id: UUID | None = None
    retryable: bool
