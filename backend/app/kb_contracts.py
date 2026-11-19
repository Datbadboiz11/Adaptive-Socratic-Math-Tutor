"""KB runtime v1. Scope is server-owned; original Member 2 proposal stays immutable."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.contracts import Contract, Identifier, Review
from app.manage import digest
from app.member2_contracts import ContentRef, RetrievalQuery, ServerRetrievalScope, TeachingChunk

KB_VERSION = "kb-1.0.0"
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Namespace = Annotated[str, Field(pattern=r"^(runtime|fixture-[A-Za-z0-9-]{1,50})$")]


class EmbeddingProfile(Contract):
    version: Literal["embedding-1.0.0"] = "embedding-1.0.0"
    provider: Literal["fastembed", "synthetic_fixture"]
    model_name: Annotated[str, Field(min_length=1, max_length=160)]
    revision: Identifier
    dimension: Annotated[int, Field(strict=True, ge=1, le=4096)]
    distance: Literal["cosine"] = "cosine"
    normalization: Literal["l2"] = "l2"
    query_prefix: Literal[""] = ""
    passage_prefix: Literal[""] = ""
    files_sha256: dict[str, Sha256] = Field(default_factory=dict)
    runtime_versions: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def pinned_model(self):
        if self.provider == "fastembed":
            expected = {"config.json", "model_optimized.onnx", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json"}
            if set(self.files_sha256) != expected or not self.runtime_versions:
                raise ValueError("Local model requires pinned files and inference runtime versions")
        return self

    @property
    def profile_id(self):
        return digest(self.model_dump(mode="json"))


class ChunkProvenance(Contract):
    registry_hash: Sha256
    pack_hash: Sha256
    pack_version: Identifier
    origin: Annotated[str, Field(min_length=1, max_length=500)]
    alignment_source_id: Identifier
    alignment_locator: Annotated[str, Field(min_length=1, max_length=2000)]
    projector_version: Literal[KB_VERSION] = KB_VERSION


class KBChunk(TeachingChunk):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    family_id: Identifier | None = None
    lineage_ids: list[Identifier] = Field(default_factory=list)
    provenance: ChunkProvenance

    @model_validator(mode="after")
    def example_exclusions(self):
        if self.kind == "example" and (not self.family_id or not self.lineage_ids):
            raise ValueError("Different examples require family and lineage exclusions")
        if len(self.lineage_ids) != len(set(self.lineage_ids)):
            raise ValueError("Duplicate lineage")
        return self

    @property
    def content_hash(self):
        return digest(self.model_dump(mode="json"))

    @property
    def text_hash(self):
        import hashlib
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def for_generator(self):
        # No references, review identities, ranking scores, embeddings or source pack.
        return self.model_dump(mode="json", include={"content_id", "content_version", "concept_id", "skill_ids",
            "kind", "text", "hint_level", "counts_as_assistance", "disclosure", "source", "problem_id"})


class ExamplePublication(Contract):
    """Explicitly reviewed teaching text; never derive an example from private solutions."""
    case_id: Identifier
    pack_hash: Sha256
    family_id: Identifier
    source_group: Identifier
    lineage_ids: list[Identifier] = Field(min_length=1)
    difficulty: Literal["introductory", "standard"]
    teaching_text: Annotated[str, Field(min_length=1, max_length=2000)]
    review: Review


class KBScope(ServerRetrievalScope):
    namespace: Namespace = "runtime"
    excluded_family_ids: list[Identifier] = Field(min_length=1)
    excluded_lineage_ids: list[Identifier] = Field(min_length=1)


class KBRequest(Contract):
    request_id: UUID
    query: RetrievalQuery
    scope: KBScope
    method: Literal["direct", "metadata", "semantic"] = "semantic"
    direct_ref: ContentRef | None = None

    @model_validator(mode="after")
    def authorization(self):
        if (self.query.concept_id, self.query.target_skill_id) not in {
                (t.concept_id, t.skill_id) for t in self.scope.allowed_targets}:
            raise ValueError("Query exceeds server-authorized concept/skill pairs")
        if (self.method == "direct") != (self.direct_ref is not None):
            raise ValueError("Direct lookup requires an exact content ID and version")
        return self


class KBResult(Contract):
    contract_version: Literal[KB_VERSION] = KB_VERSION
    retrieval_id: UUID
    request_id: UUID
    kb_snapshot_version: Identifier
    snapshot_manifest_hash: Sha256 | None = None
    registry_version: Identifier | None = None
    retrieval_config_version: Literal[KB_VERSION] = KB_VERSION
    method: Literal["direct", "metadata", "semantic"]
    embedding_version: Sha256 | None = None
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    eligible_count: int = Field(ge=0)
    chunks: list[KBChunk] = Field(max_length=10)
    fallback_reason: Literal["no_eligible_content", "retrieval_unavailable", "snapshot_unavailable"] | None = None

    @model_validator(mode="after")
    def consistency(self):
        if bool(self.chunks) == (self.fallback_reason is not None):
            raise ValueError("Empty results need an explicit fallback; populated results cannot be fallback")
        if self.chunks and (not self.snapshot_manifest_hash or not self.registry_version
                            or (self.method == "semantic" and not self.embedding_version)):
            raise ValueError("Retrieved chunks require complete snapshot/model provenance")
        keys = [(c.content_id, c.content_version) for c in self.chunks]
        if len(keys) != len(set(keys)) or self.eligible_count < len(keys):
            raise ValueError("Invalid candidate count or duplicate result")
        return self


def validate_result(request: KBRequest, result: KBResult):
    if request.request_id != result.request_id or request.scope.kb_snapshot_version != result.kb_snapshot_version:
        raise ValueError("Retrieval correlation/snapshot mismatch")
    if result.method != request.method or len(result.chunks) > request.query.top_k:
        raise ValueError("Method/top-K mismatch")
    scope, query = request.scope, request.query
    for chunk in result.chunks:
        if (chunk.concept_id != query.concept_id or query.target_skill_id not in chunk.skill_ids
                or chunk.kind != query.purpose or chunk.hint_level > scope.allowed_hint_level
                or not set(chunk.grade_levels).intersection(scope.grade_levels)
                or (chunk.difficulty is not None and chunk.difficulty != scope.difficulty)
                or chunk.problem_id == scope.active_problem_id
                or chunk.source_group in scope.excluded_source_groups):
            raise ValueError("Retrieved content exceeds server scope")
        if chunk.kind == "example" and (chunk.family_id in scope.excluded_family_ids
                or set(chunk.lineage_ids).intersection(scope.excluded_lineage_ids)):
            raise ValueError("Different example is too close to the current measurement")
        if request.direct_ref and (chunk.content_id, chunk.content_version) != (
                request.direct_ref.content_id, request.direct_ref.content_version):
            raise ValueError("Direct lookup returned a different version")
    return result
