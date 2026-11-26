from typing import Literal
from uuid import UUID
from pydantic import ConfigDict, Field, AwareDatetime, model_validator
from app.contracts import Contract, Identifier, ProblemPublic, SessionPublic, Assessment, Eligibility, TurnRequest
from app.curriculum import AuthoringTaskKind
from app.member2_problem_contract import PublicProblemV3


class DemoLogin(Contract):
    demo_profile_id: Identifier


class ApiErrorBody(Contract):
    code: str
    message: str
    retryable: bool
    trace_id: UUID | None = None


class TopicView(Contract):
    topic_id: Identifier
    title: str
    problem_count: int
    tutoring_ready: bool
    internal_demo_available: bool
    validator_available: bool
    validator_task_kinds: list[AuthoringTaskKind]
    reason: str


class Mutation(Contract):
    request_id: UUID
    expected_state_version: int = Field(ge=1)


class SaveDraft(Mutation):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    draft: str = Field(max_length=2000)


class TeachingTurnRequest(TurnRequest):
    action: Literal['submit','request_hint','request_explanation','request_example']

    @model_validator(mode='after')
    def support_is_not_a_submission(self):
        if self.action != 'submit' and self.steps:
            raise ValueError('Support requests cannot submit an answer')
        return self


class ContentCitation(Contract):
    content_id: Identifier
    content_version: str
    title: str
    kind: Literal['explanation','hint','example']


class TutorResponseView(Contract):
    # Project the public delivery receipt, never the internal retrieval scope/context.
    model_config = ConfigDict(extra='ignore')
    message: str
    response_source: str
    action: str | None = None
    hint_level: int = 0
    content_review_status: str | None = None
    counts_as_assistance: bool = False
    content_refs: list[ContentCitation] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    fallback_reason: str | None = None
    policy_version: str | None = None
    prompt_version: str | None = None
    model: str | None = None
    model_response_id: str | None = None
    usage: dict | None = None


class TurnPublic(Contract):
    turn_id: UUID
    opportunity_id: UUID
    request_id: UUID
    action: Literal['submit', 'request_hint','request_explanation','request_example']
    steps: list[str]
    assessment: Assessment
    response: TutorResponseView
    created_at: AwareDatetime


class SessionView(SessionPublic):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    problem: ProblemPublic | PublicProblemV3
    mode: Literal['internal_demo'] = 'internal_demo'
    review_status: str
    tutoring_enabled: bool = False
    mastery: list[dict] = Field(default_factory=list)
    relation: str
    turns: list[TurnPublic]
    eligible_observations: int
    available_next: int
    assistance_received: bool = False
    rag_mode: Literal['full','no_rag'] = 'no_rag'


class TurnResult(Contract):
    session: SessionView
    assessment: Assessment
    eligibility: Eligibility
    message: str
    response_source: Literal['system_unavailable','openai','gemini','draft_template','reviewed_hint','reviewed_kb','assessment_feedback'] = 'system_unavailable'
    tutor: TutorResponseView | None = None
    observation: dict | None = None


class SkillReport(Contract):
    concept_id: str
    skill_id: str
    title: str
    problems_viewed: int
    independent_correct: int
    assisted_correct: int
    repeat_or_near_correct: int
    unverified_submissions: int
    incorrect_submissions: int
    observation_ids: list[UUID]
    mastery_before: float | None = None
    mastery_after: float | None = None
    evidence_count_before: int | None = None
    evidence_count_after: int | None = None
    other_session_observations: int = 0
    parameter_version: str | None = None
    parameter_source: str | None = None
    updated_at: AwareDatetime | None = None
    review_reason: str | None = None
    evidence_turn_ids: list[UUID] = Field(default_factory=list)


class Report(Contract):
    tutoring_enabled: bool = False
    mastery: list[dict] = Field(default_factory=list)
    session_id: UUID
    status: Literal['active', 'paused', 'completed']
    independent_correct: int
    assisted_correct: int
    repeat_or_near_correct: int = 0
    assessment_scope: Literal['solution_steps','final_answer'] = 'solution_steps'
    valid_observations: int
    unverified_submissions: int
    submitted_turns: int
    problems_viewed: int
    requested_hints: int
    completed_at: AwareDatetime | None
    timeline: list[TurnPublic]
    limitations: list[str]
    report_version: Literal['learning-report-2.0.0'] = 'learning-report-2.0.0'
    skills: list[SkillReport] = Field(default_factory=list)
