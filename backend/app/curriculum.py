"""Versioned authoring registry. Draft content is never published implicitly."""
from collections import deque
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator
from app.contracts import Contract, Identifier, Review

CONTENT_ROOT = Path(__file__).resolve().parents[2] / 'content' / 'curriculum'
Text = Annotated[str, Field(min_length=1, max_length=2000)]
TaskKind = Literal['numeric', 'evaluate', 'polynomial', 'linear_equation', 'quadratic_vertex']


class Source(Contract):
    source_id: Identifier
    title: Text
    url: Text
    publisher: Text
    accessed_on: str
    note: Text


class Alignment(Contract):
    grade_levels: list[Annotated[int, Field(ge=6, le=12)]] = Field(min_length=1)
    status: Literal['proposed', 'source_checked_draft', 'human_approved']
    source_id: Identifier
    locator: Text
    reviewer: str | None = None

    @model_validator(mode='after')
    def approved_alignment_requires_reviewer(self):
        if self.status == 'human_approved' and not self.reviewer:
            raise ValueError('Curriculum alignment approval requires a reviewer')
        return self


class Skill(Contract):
    skill_id: Identifier
    observable_behavior: Text


class Concept(Contract):
    concept_id: Annotated[str, Field(pattern=r'^[NAEF](0[1-9]|10)$')]
    title: Text
    strand: Literal['numbers', 'algebra', 'equations', 'functions']
    objective: Text
    skills: list[Skill] = Field(min_length=1)
    supported_forms: list[Text] = Field(min_length=1)
    excluded_forms: list[Text] = Field(min_length=1)
    authoring_task_kinds: list[TaskKind] = Field(default_factory=list)
    alignment: Alignment
    pilot: bool
    review: Review


class Edge(Contract):
    edge_id: Identifier
    source_concept_id: Identifier
    target_concept_id: Identifier
    relation: Literal['PREREQUISITE_OF', 'RELATED_TO', 'PART_OF']
    rationale: Text
    source_id: Identifier
    review: Review


class LegacyMapping(Contract):
    legacy_concept_id: Identifier
    legacy_skill_id: Identifier
    concept_id: Identifier
    skill_id: Identifier
    status: Literal['proposed']
    note: Text


class CurriculumRegistry(Contract):
    schema_version: Literal['1.0.0']
    content_version: str
    sources: list[Source] = Field(min_length=1)
    concepts: list[Concept] = Field(min_length=30, max_length=50)
    edges: list[Edge]
    legacy_mappings: list[LegacyMapping]

    @model_validator(mode='after')
    def references_and_dag(self):
        def unique(values, name):
            if len(values) != len(set(values)):
                raise ValueError(f'Duplicate {name}')
        ids = [c.concept_id for c in self.concepts]
        skills = [s.skill_id for c in self.concepts for s in c.skills]
        sources = [s.source_id for s in self.sources]
        unique(ids, 'concept ID'); unique(skills, 'skill ID'); unique(sources, 'source ID')
        unique([e.edge_id for e in self.edges], 'edge ID')
        unique([(e.source_concept_id, e.target_concept_id, e.relation) for e in self.edges], 'edge')
        mapping = {c.concept_id: c for c in self.concepts}
        for c in self.concepts:
            if c.strand != {'N': 'numbers', 'A': 'algebra', 'E': 'equations', 'F': 'functions'}[c.concept_id[0]]:
                raise ValueError('Concept ID and strand disagree')
            unique(c.alignment.grade_levels, 'grade level')
            if c.alignment.source_id not in sources:
                raise ValueError('Unknown curriculum source')
            if c.review.status == 'human_approved' and c.alignment.status != 'human_approved':
                raise ValueError('Published concept needs approved curriculum alignment')
        graph, indegree = {i: [] for i in ids}, {i: 0 for i in ids}
        for edge in self.edges:
            a, b = edge.source_concept_id, edge.target_concept_id
            if a not in mapping or b not in mapping or a == b or edge.source_id not in sources:
                raise ValueError('Invalid edge reference or self edge')
            if edge.relation == 'PREREQUISITE_OF':
                graph[a].append(b); indegree[b] += 1
        queue = deque(i for i in ids if indegree[i] == 0)
        visited = 0
        while queue:
            current = queue.popleft(); visited += 1
            for target in graph[current]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if visited != len(ids):
            raise ValueError('Prerequisite graph contains a cycle')
        for alias in self.legacy_mappings:
            if alias.concept_id not in mapping or alias.skill_id not in {s.skill_id for s in mapping[alias.concept_id].skills}:
                raise ValueError('Invalid proposed legacy mapping')
        return self


class MathTask(Contract):
    kind: TaskKind
    expression: Annotated[str, Field(min_length=1, max_length=160)]
    variable_value: str | None = None

    @model_validator(mode='after')
    def substitution_matches_task_kind(self):
        if self.kind == 'evaluate' and not self.variable_value:
            raise ValueError('Evaluation requires a value for x')
        if self.kind != 'evaluate' and self.variable_value is not None:
            raise ValueError('Only evaluation tasks accept a value for x')
        return self


class MathCase(Contract):
    case_id: Identifier
    task: MathTask
    reference_answer: Annotated[str, Field(min_length=1, max_length=160)]
    reference_steps: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(min_length=1, max_length=12)


class AuthoredProblem(MathCase):
    concept_id: Identifier
    primary_skill_id: Identifier
    family_id: Identifier
    source_group: Identifier
    difficulty: Literal['introductory', 'standard']
    prompt: Text
    split: Literal['authoring_dev']
    origin: Text


class ErrorFixture(Contract):
    error_id: Identifier
    problem_id: Identifier
    response_steps: list[str] = Field(min_length=1, max_length=12)
    first_error_step: int = Field(ge=1)
    family: Text
    hypothesis: Text
    diagnostic_question: Text
    diagnosis_status: Literal['suspected']


class Hint(Contract):
    level: Annotated[int, Field(ge=1, le=3)]
    text: Text
    disclosure: Literal['conceptual', 'strategy', 'scaffold']


class ConceptPack(Contract):
    concept_id: Identifier
    content_version: str
    explanation: Text
    problems: list[AuthoredProblem] = Field(min_length=6)
    examples: list[MathCase] = Field(min_length=3)
    errors: list[ErrorFixture] = Field(min_length=1)
    hints: list[Hint] = Field(min_length=3, max_length=3)
    review: Review

    @model_validator(mode='after')
    def content_coverage(self):
        ids = [p.case_id for p in self.problems]
        if len(ids) != len(set(ids)) or len({e.case_id for e in self.examples}) != len(self.examples):
            raise ValueError('Duplicate problem/example ID')
        if any(p.concept_id != self.concept_id for p in self.problems):
            raise ValueError('Wrong concept in pack')
        if len({p.family_id for p in self.problems}) < 3:
            raise ValueError('At least three problem families required')
        if [h.level for h in self.hints] != [1, 2, 3] or [h.disclosure for h in self.hints] != ['conceptual', 'strategy', 'scaffold']:
            raise ValueError('Ordered hint ladder required')
        if len({e.error_id for e in self.errors}) != len(self.errors):
            raise ValueError('Duplicate error fixture ID')
        for error in self.errors:
            if error.problem_id not in ids or error.first_error_step > len(error.response_steps):
                raise ValueError('Invalid error fixture reference')
        return self


class PilotBank(Contract):
    schema_version: Literal['1.0.0']
    content_version: str
    packs: list[ConceptPack] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_ids_and_versions(self):
        ids = [p.concept_id for p in self.packs]
        records = [r.case_id for p in self.packs for r in [*p.problems, *p.examples]]
        if len(ids) != len(set(ids)) or len(records) != len(set(records)):
            raise ValueError('Duplicate pilot concept or record ID')
        if any(p.content_version != self.content_version for p in self.packs):
            raise ValueError('Mixed pilot versions')
        return self


def load_curriculum(root=CONTENT_ROOT):
    registry = CurriculumRegistry.model_validate_json((root / 'registry.v1.json').read_text(encoding='utf-8'))
    bank = PilotBank.model_validate_json((root / 'pilot.v1.json').read_text(encoding='utf-8'))
    concepts = {c.concept_id: c for c in registry.concepts}
    if bank.content_version != registry.content_version:
        raise ValueError('Registry/pilot version mismatch')
    if set(c.concept_id for c in registry.concepts if c.pilot) != {p.concept_id for p in bank.packs}:
        raise ValueError('Declared pilot coverage mismatch')
    for pack in bank.packs:
        valid = {s.skill_id for s in concepts[pack.concept_id].skills}
        if any(p.primary_skill_id not in valid for p in pack.problems):
            raise ValueError('Problem references unknown skill')
        if any(c.task.kind not in concepts[pack.concept_id].authoring_task_kinds for c in [*pack.problems, *pack.examples]):
            raise ValueError('Task kind is outside the declared concept authoring scope')
    return registry, bank


def prerequisite_candidates(registry, concept_id, max_depth=2, *, authoring=False):
    """Edge A -> B: A is required before B. Public traversal excludes drafts."""
    if max_depth not in (1, 2):
        raise ValueError('Only one or two prerequisite levels supported')
    concepts = {c.concept_id: c for c in registry.concepts}
    if concept_id not in concepts:
        raise ValueError('Unknown concept')
    edges = [e for e in registry.edges if e.relation == 'PREREQUISITE_OF' and
             (authoring or (e.review.status == 'human_approved' and
              concepts[e.source_concept_id].review.status == 'human_approved' and
              concepts[e.target_concept_id].review.status == 'human_approved'))]
    queue, seen, result = deque([(concept_id, 0)]), {concept_id}, []
    while queue:
        target, depth = queue.popleft()
        if depth == max_depth:
            continue
        for edge in sorted(edges, key=lambda e: e.edge_id):
            if edge.target_concept_id == target and edge.source_concept_id not in seen:
                seen.add(edge.source_concept_id)
                result.append({'concept_id': edge.source_concept_id, 'edge_id': edge.edge_id,
                               'target_concept_id': target, 'depth': depth + 1})
                queue.append((edge.source_concept_id, depth + 1))
    return result


def safe_chunks(registry, bank, concept_id, level=1):
    """Direct metadata lookup foundation; no reference solutions or draft publication.

    This is not semantic RAG. It supplies only approved explanation/hint content.
    """
    if level not in (1, 2, 3):
        raise ValueError('Invalid hint level')
    concept = next((c for c in registry.concepts if c.concept_id == concept_id), None)
    pack = next((p for p in bank.packs if p.concept_id == concept_id), None)
    if concept is None or pack is None or concept.review.status != 'human_approved' or concept.alignment.status != 'human_approved' or pack.review.status != 'human_approved':
        return []
    metadata = {'content_version': bank.content_version, 'concept_id': concept_id,
                'skill_ids': [s.skill_id for s in concept.skills], 'grade_levels': concept.alignment.grade_levels,
                'review_status': pack.review.status, 'source': pack.review.source,
                'curriculum_source_id': concept.alignment.source_id, 'reviewer': pack.review.human_reviewer}
    return [{**metadata, 'content_id': f'{concept_id}-explanation',
             'kind': 'explanation', 'disclosure': 'conceptual', 'text': pack.explanation},
            *[{**metadata, 'content_id': f'{concept_id}-hint-{h.level}',
               'kind': 'hint', 'disclosure': h.disclosure, 'text': h.text}
              for h in pack.hints if h.level <= level]]
