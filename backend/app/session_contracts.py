from typing import Literal
from uuid import UUID
from pydantic import ConfigDict, Field, AwareDatetime
from app.contracts import Contract, Identifier, SessionPublic, Assessment, Eligibility


class DemoLogin(Contract):
    demo_profile_id: Identifier


class ApiErrorBody(Contract):
    code: str
    message: str
    retryable: bool
    trace_id: UUID | None = None


class Mutation(Contract):
    request_id: UUID
    expected_state_version: int = Field(ge=1)


class SaveDraft(Mutation):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    draft: str = Field(max_length=2000)


class TurnPublic(Contract):
    turn_id: UUID
    opportunity_id: UUID
    request_id: UUID
    action: Literal['submit', 'request_hint']
    steps: list[str]
    assessment: Assessment
    response: dict
    created_at: AwareDatetime


class SessionView(SessionPublic):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    mode: Literal['internal_demo'] = 'internal_demo'
    review_status: str
    tutoring_enabled: bool = False
    mastery: list[dict] = Field(default_factory=list)
    relation: str
    turns: list[TurnPublic]
    eligible_observations: int
    available_next: int


class TurnResult(Contract):
    session: SessionView
    assessment: Assessment
    eligibility: Eligibility
    message: str
    response_source: Literal['system_unavailable','openai','draft_template'] = 'system_unavailable'
    tutor: dict | None = None
    observation: dict | None = None


class Report(Contract):
    tutoring_enabled: bool = False
    mastery: list[dict] = Field(default_factory=list)
    session_id: UUID
    status: Literal['active', 'paused', 'completed']
    independent_correct: int
    assisted_correct: int
    valid_observations: int
    unverified_submissions: int
    submitted_turns: int
    problems_viewed: int
    requested_hints: int
    completed_at: AwareDatetime | None
    timeline: list[TurnPublic]
    limitations: list[str]
