"""Proposed Member 2 interfaces; deliberately not imported by the running API.

These are data contracts, not authorization or mathematical verification.
Retrieval scopes must be constructed from trusted session/policy state by a server.
"""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.contracts import Contract, Identifier, Probability, Review
from app.curriculum import AuthoredProblem, CurriculumRegistry, MathTask

VERSION = "member2-proposal-0.2.0"
Version = Annotated[str, Field(min_length=1, max_length=80)]
Text = Annotated[str, Field(min_length=1, max_length=2000)]
ConceptId = Annotated[str, Field(pattern=r"^[NAEF](0[1-9]|10)$")]
HintLevel = Annotated[int, Field(strict=True, ge=0, le=3)]
Count = Annotated[int, Field(strict=True, ge=0)]
Difficulty = Literal["introductory", "standard"]


class PublicTask(MathTask):
    """The kind selects the task; expression/value are public problem inputs."""
    variable_value: Annotated[str, Field(min_length=1, max_length=160)] | None = None


class CurriculumProblemPublic(Contract):
    contract_version: Literal[VERSION] = VERSION
    problem_id: Identifier
    content_version: Version
    concept_id: ConceptId
    primary_skill_id: Identifier
    family_id: Identifier
    prompt: Text
    task: PublicTask
    domain: Literal["real_numbers"] = "real_numbers"
    difficulty: Difficulty


class ConceptReadiness(Contract):
    """Evidence gates for canonical curriculum; client flags cannot activate a topic."""
    concept_id: ConceptId
    has_pack: bool
    alignment_approved: bool
    concept_approved: bool
    pack_approved: bool
    prerequisites_approved: bool
    validator_integrated: bool
    ui_policy_verified: bool
    contract_review_complete: bool

    @property
    def blockers(self) -> list[str]:
        return [name for name in type(self).model_fields
                if name != "concept_id" and not getattr(self, name)]

    @property
    def ready(self) -> bool:
        return not self.blockers


def project_problem(problem: AuthoredProblem, content_version: str) -> CurriculumProblemPublic:
    """Explicit projection of an authoring record, not permission to publish it."""
    return CurriculumProblemPublic(
        problem_id=problem.case_id, content_version=content_version,
        concept_id=problem.concept_id, primary_skill_id=problem.primary_skill_id,
        family_id=problem.family_id, prompt=problem.prompt,
        task=PublicTask.model_validate(problem.task.model_dump()), difficulty=problem.difficulty,
    )


class ContentRef(Contract):
    content_id: Identifier
    content_version: Version


class ContentSource(Contract):
    source_id: Identifier
    title: Text
    locator: Text


class TeachingChunk(Contract):
    content_id: Identifier
    content_version: Version
    concept_id: ConceptId
    skill_ids: list[Identifier] = Field(min_length=1)
    kind: Literal["explanation", "hint", "example"]
    text: Text
    hint_level: HintLevel
    # Classification only. Retrieval is not delivery and must not update learner state.
    counts_as_assistance: Literal[True] = True
    disclosure: Literal["conceptual", "strategy", "scaffold", "different_example"]
    grade_levels: list[Annotated[int, Field(strict=True, ge=6, le=12)]] = Field(min_length=1)
    difficulty: Difficulty | None = None
    source: ContentSource
    review: Review
    problem_id: Identifier | None = None
    source_group: Identifier | None = None

    @model_validator(mode="after")
    def allowed_teaching_content(self):
        if self.review.status != "human_approved":
            raise ValueError("Retrievable teaching chunks require human review provenance")
        for values in (self.skill_ids, self.grade_levels):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate skill or grade")
        if self.kind == "explanation":
            if self.hint_level != 0 or self.disclosure != "conceptual":
                raise ValueError("Explanation uses conceptual disclosure at level zero")
        elif self.kind == "hint":
            expected = {1: "conceptual", 2: "strategy", 3: "scaffold"}
            if expected.get(self.hint_level) != self.disclosure:
                raise ValueError("Hint level/disclosure disagree")
        elif (self.hint_level != 3 or self.disclosure != "different_example"
              or not self.problem_id or not self.source_group):
            raise ValueError("Different examples require level three and exclusion metadata")
        return self


class RetrievalQuery(Contract):
    query: Text
    concept_id: ConceptId
    target_skill_id: Identifier
    purpose: Literal["explanation", "hint", "example"]
    top_k: int = Field(default=3, strict=True, ge=1, le=10)


class ConceptSkillTarget(Contract):
    concept_id: ConceptId
    skill_id: Identifier


class ServerRetrievalScope(Contract):
    """Internal only: never accept this object from student HTTP payloads/LLM tools."""
    session_id: UUID
    opportunity_id: UUID
    allowed_targets: list[ConceptSkillTarget] = Field(min_length=1)
    allowed_hint_level: HintLevel
    kb_snapshot_version: Version
    active_problem_id: Identifier
    excluded_source_groups: list[Identifier] = Field(min_length=1)
    grade_levels: list[Annotated[int, Field(strict=True, ge=6, le=12)]] = Field(min_length=1)
    difficulty: Difficulty

    @model_validator(mode="after")
    def unique_targets(self):
        pairs = [(t.concept_id, t.skill_id) for t in self.allowed_targets]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Duplicate authorized concept/skill pair")
        return self

    @classmethod
    def from_registry(cls, registry: CurriculumRegistry, **data):
        """Construct a server scope after checking every allowed pair against the registry."""
        scope = cls.model_validate(data)
        valid = {(c.concept_id, s.skill_id) for c in registry.concepts for s in c.skills}
        if any((t.concept_id, t.skill_id) not in valid for t in scope.allowed_targets):
            raise ValueError("Authorized target is not a concept/skill pair in the registry")
        return scope


class RetrievalRequest(Contract):
    contract_version: Literal[VERSION] = VERSION
    request_id: UUID
    query: RetrievalQuery
    scope: ServerRetrievalScope

    @model_validator(mode="after")
    def query_within_server_permissions(self):
        pair = (self.query.concept_id, self.query.target_skill_id)
        if pair not in {(t.concept_id, t.skill_id) for t in self.scope.allowed_targets}:
            raise ValueError("Query exceeds server-authorized concept/skill pairs")
        return self


class RetrievalResult(Contract):
    retrieval_id: UUID
    request_id: UUID
    kb_snapshot_version: Version
    retrieval_config_version: Version
    method: Literal["direct", "metadata", "semantic"]
    embedding_version: Version | None = None
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    chunks: list[TeachingChunk] = Field(max_length=10)
    fallback_reason: Literal["no_eligible_content", "retrieval_unavailable"] | None = None

    @model_validator(mode="after")
    def consistent_result(self):
        if bool(self.chunks) == (self.fallback_reason is not None):
            raise ValueError("Empty results require a reason; populated results cannot be fallback")
        if self.method == "semantic" and not self.embedding_version:
            raise ValueError("Semantic retrieval requires embedding version")
        keys = [(c.content_id, c.content_version) for c in self.chunks]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate retrieved chunk/version")
        return self


class RetrievalExchange(Contract):
    """Cross-check a result against the server scope before it reaches a generator."""
    request: RetrievalRequest
    result: RetrievalResult

    @model_validator(mode="after")
    def scope_matches_result(self):
        request, result = self.request, self.result
        query, scope = request.query, request.scope
        if request.request_id != result.request_id or scope.kb_snapshot_version != result.kb_snapshot_version:
            raise ValueError("Retrieval correlation/snapshot mismatch")
        if len(result.chunks) > query.top_k:
            raise ValueError("Result exceeds requested top K")
        for chunk in result.chunks:
            if (chunk.concept_id != query.concept_id or query.target_skill_id not in chunk.skill_ids
                    or chunk.kind != query.purpose):
                raise ValueError("Retrieved content is outside the requested teaching scope")
            if chunk.hint_level > scope.allowed_hint_level:
                raise ValueError("Retrieved content exceeds allowed support")
            if not set(chunk.grade_levels).intersection(scope.grade_levels):
                raise ValueError("Retrieved content is outside grade scope")
            if chunk.difficulty is not None and chunk.difficulty != scope.difficulty:
                raise ValueError("Retrieved content is outside difficulty scope")
            if (chunk.problem_id == scope.active_problem_id
                    or chunk.source_group in scope.excluded_source_groups):
                raise ValueError("Current problem or excluded source group was retrieved")
        return self


class TutorPresentation(Contract):
    contract_version: Literal[VERSION] = VERSION
    opportunity_id: UUID
    action: Literal["ask", "hint", "different_example", "confirm", "clarify", "offer_pause"]
    active_problem_id: Identifier
    message: Text
    hint_level: HintLevel
    assistance_provided: bool = Field(strict=True)
    response_source: Literal["openai", "draft_template", "reviewed_fallback", "system_unavailable"]
    content_review_status: Literal["draft", "machine_checked", "human_approved"]
    content_refs: list[ContentRef]
    policy_version: Version
    different_example: CurriculumProblemPublic | None = None

    @model_validator(mode="after")
    def consistent_presentation(self):
        if (self.action in ("hint", "different_example") or self.content_refs) and not self.assistance_provided:
            raise ValueError("Teaching content or a hint must be recorded as assistance")
        if (self.action == "different_example") != (self.different_example is not None):
            raise ValueError("A different-example action requires a separate public task")
        if self.action == "different_example" and self.hint_level != 3:
            raise ValueError("Different examples use support level three in this proposal")
        if self.different_example is not None and self.different_example.problem_id == self.active_problem_id:
            raise ValueError("A different example must not be the active problem")
        refs = [(r.content_id, r.content_version) for r in self.content_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("Duplicate content citation")
        if self.response_source == "reviewed_fallback" and self.content_review_status != "human_approved":
            raise ValueError("Draft templates cannot be labelled reviewed fallback")
        return self


class OpportunityAssistance(Contract):
    """Server-owned summary, committed with a delivered turn, never on retrieval alone."""
    opportunity_id: UUID
    problem_id: Identifier
    target_skill_id: Identifier
    assistance_level: HintLevel
    assistance_received: bool = Field(strict=True)

    @model_validator(mode="after")
    def consistent_history(self):
        if self.assistance_level > 0 and not self.assistance_received:
            raise ValueError("Nonzero historical support cannot be marked independent")
        return self

    def record_delivery(self, presentation: TutorPresentation):
        if (presentation.opportunity_id != self.opportunity_id
                or presentation.active_problem_id != self.problem_id):
            raise ValueError("Delivered response belongs to a different opportunity/problem")
        return type(self).model_validate({
            **self.model_dump(),
            "assistance_received": self.assistance_received or presentation.assistance_provided,
            "assistance_level": max(self.assistance_level, presentation.hint_level),
        })


class SkillReport(Contract):
    concept_id: ConceptId
    skill_id: Identifier
    session_observations: Count
    session_observation_ids: list[UUID]
    other_session_observations: Count
    evidence_count_before: Count
    evidence_count_after: Count
    mastery_before: Probability | None
    mastery_after: Probability | None
    parameter_version: Version | None
    parameter_source: Literal["bootstrap", "default", "pooled", "fitted"] | None
    updated_at: AwareDatetime | None

    @model_validator(mode="after")
    def evidence_snapshot(self):
        if (len(self.session_observation_ids) != len(set(self.session_observation_ids))
                or len(self.session_observation_ids) != self.session_observations):
            raise ValueError("Session count must equal distinct observation IDs from this session")
        if (self.evidence_count_after - self.evidence_count_before !=
                self.session_observations + self.other_session_observations):
            raise ValueError("Cumulative evidence must reconcile with own and interleaved observations")
        state = [self.mastery_before, self.mastery_after, self.parameter_version,
                 self.parameter_source, self.updated_at]
        if any(v is None for v in state) and any(v is not None for v in state):
            raise ValueError("Mastery snapshot requires both states and parameter provenance")
        if self.evidence_count_after > 0 and self.mastery_after is None:
            raise ValueError("Observed skills require a state snapshot")
        if self.session_observations == 0 and (
                self.mastery_before != self.mastery_after or self.other_session_observations != 0):
            raise ValueError("No own observation: retain the unchanged session snapshot")
        return self


class LearningReportSnapshot(Contract):
    """Server-computed, end-of-session facts; no client/LLM tallying."""
    contract_version: Literal[VERSION] = VERSION
    session_id: UUID
    state_version: int = Field(strict=True, ge=1)
    status: Literal["completed"]
    completed_at: AwareDatetime
    independent_correct: Count
    assisted_correct: Count
    unverified_submissions: Count
    valid_observations: Count
    skills: list[SkillReport]
    limitations: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def reconcile_observations(self):
        if len({s.skill_id for s in self.skills}) != len(self.skills):
            raise ValueError("Duplicate skill snapshot")
        if sum(s.session_observations for s in self.skills) != self.valid_observations:
            raise ValueError("Report total must equal per-skill session observations")
        observation_ids = [oid for s in self.skills for oid in s.session_observation_ids]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("One observation cannot count toward multiple skills")
        if any(s.updated_at is not None and s.updated_at > self.completed_at for s in self.skills):
            raise ValueError("Completed reports cannot use future skill state")
        return self


class FoundationExamples(Contract):
    contract_version: Literal[VERSION]
    fixture_origin: Literal["synthetic_contract_examples_not_reviewed_curriculum"]
    problems: list[CurriculumProblemPublic] = Field(min_length=5)
    readiness: list[ConceptReadiness] = Field(min_length=1)
    retrieval_exchanges: list[RetrievalExchange] = Field(min_length=1)
    tutor_presentations: list[TutorPresentation] = Field(min_length=1)
    assistance_states: list[OpportunityAssistance] = Field(min_length=1)
    reports: list[LearningReportSnapshot] = Field(min_length=1)
