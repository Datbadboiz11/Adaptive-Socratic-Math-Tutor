"""Versioned public projections for curriculum and existing demo problems."""
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from app.contracts import Contract, ProblemPublic
from app.curriculum import AuthoredProblem, AuthoringMathTask
from app.member2_contracts import ConceptId, CurriculumProblemPublic

VERSION = "member2-proposal-0.3.0"
LEGACY_TOPIC = "TOPIC-LINEAR-01"
LEGACY_CONCEPT = "CON-LINEAR-01"
LEGACY_SKILL = "SK-LIN-SOLVE"


class PublicTask(AuthoringMathTask):
    variable_value: Annotated[str, Field(min_length=1, max_length=160)] | None = None


class PublicProblemV3(CurriculumProblemPublic):
    contract_version: Literal[VERSION] = VERSION
    concept_id: ConceptId | Literal[LEGACY_CONCEPT]
    task: PublicTask


class PublicProblemExamples(Contract):
    curriculum_drafts: list[PublicProblemV3] = Field(min_length=1)
    legacy_demo: PublicProblemV3


def project_curriculum_problem(problem: AuthoredProblem, content_version: str) -> PublicProblemV3:
    """Project public fields. The caller still needs publication and readiness evidence."""
    return PublicProblemV3(
        problem_id=problem.case_id, content_version=content_version,
        concept_id=problem.concept_id, primary_skill_id=problem.primary_skill_id,
        family_id=problem.family_id, prompt=problem.prompt, difficulty=problem.difficulty,
        task=PublicTask.model_validate(problem.task.model_dump()),
    )


def project_legacy_problem(problem: ProblemPublic) -> PublicProblemV3:
    """Adapt a v1 equation without changing its problem, concept, skill or version."""
    return PublicProblemV3(
        **problem.model_dump(exclude={"equation"}),
        task=PublicTask(kind="linear_equation", expression=problem.equation),
    )


def demo_validator_task(topic_id: str, payload: dict, stored_skill_id: str) -> Literal["linear_equation"] | None:
    """The existing tutor, policy and BKT have evidence for this legacy scope only."""
    if topic_id != LEGACY_TOPIC or stored_skill_id != LEGACY_SKILL:
        return None
    try:
        problem = ProblemPublic.model_validate(payload)
        if (problem.concept_id, problem.primary_skill_id) == (LEGACY_CONCEPT, LEGACY_SKILL):
            project_legacy_problem(problem)
            return "linear_equation"
    except ValidationError:
        return None
    return None
