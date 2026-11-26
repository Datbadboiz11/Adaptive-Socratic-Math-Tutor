"""Member 3 tool boundary: bind trusted server state once; LLM arguments contain query only."""
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.curriculum import CurriculumRegistry
from app.db import connect
from app.kb_contracts import KBRequest, KBScope
from app.kb_sync import active_snapshot, KBConflict
from app.member2_contracts import ConceptSkillTarget, RetrievalQuery
from app.retrieval import KBRetriever


@dataclass(frozen=True)
class TrustedKBState:
    """Construct only in server policy code from its session/opportunity; never deserialize a client scope."""
    session_id: UUID
    opportunity_id: UUID
    concept_id: str
    target_skill_id: str
    allowed_hint_level: int
    active_problem_id: str
    active_source_group: str
    active_family_id: str
    active_lineage_ids: tuple[str, ...]
    grade_levels: tuple[int, ...]
    difficulty: str


class BoundTeachingContentTool:
    input_schema = RetrievalQuery.model_json_schema()

    def __init__(self, scope: KBScope, retriever: KBRetriever):
        self._scope = KBScope.model_validate(scope.model_dump(mode="json"))
        self._retriever = retriever

    def invoke(self, arguments, *, request_id=None):
        # Extra fields (scope/snapshot/hint permissions/exclusions) are rejected by RetrievalQuery.
        query = RetrievalQuery.model_validate(arguments)
        request = KBRequest(request_id=request_id or uuid4(),query=query,scope=self._scope)
        return self._retriever.retrieve(request)


def bind_runtime_tool(state: TrustedKBState, embedder=None, *, connection_factory=connect):
    if not isinstance(state, TrustedKBState):
        raise ValueError("Bind retrieval from trusted server state, not a client object")
    with connection_factory() as c:
        snapshot_id = active_snapshot(c, "runtime")
        if not snapshot_id:
            raise KBConflict("No active runtime KB snapshot")
        row = c.execute("""SELECT r.payload FROM kb_snapshots s JOIN kb_registry_versions r
            ON r.namespace=s.namespace AND r.registry_version=s.registry_version
            WHERE s.namespace='runtime' AND s.snapshot_id=%s""", (snapshot_id,)).fetchone()
    registry = CurriculumRegistry.model_validate(row["payload"])
    scope = KBScope.from_registry(registry,namespace="runtime",session_id=state.session_id,opportunity_id=state.opportunity_id,
        allowed_targets=[ConceptSkillTarget(concept_id=state.concept_id,skill_id=state.target_skill_id)],
        allowed_hint_level=state.allowed_hint_level,kb_snapshot_version=snapshot_id,active_problem_id=state.active_problem_id,
        excluded_source_groups=[state.active_source_group],excluded_family_ids=[state.active_family_id],
        excluded_lineage_ids=list(state.active_lineage_ids),grade_levels=list(state.grade_levels),difficulty=state.difficulty)
    return BoundTeachingContentTool(scope,KBRetriever(embedder,connection_factory))
