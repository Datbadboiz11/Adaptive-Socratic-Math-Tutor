"""Grounding contracts: retrieval supplies evidence, never an Agent decision."""
from typing import Literal
from pydantic import Field
from app.contracts import Contract, Identifier
from app.pilot_contracts import PilotAnalysis, PilotSubmission


class KnowledgeChunk(Contract):
    content_id: Identifier
    concept_id: Identifier
    skill_ids: list[Identifier]
    title: str
    text: str = Field(min_length=1, max_length=2000)
    kind: Literal['explanation', 'hint']
    hint_level: int = Field(ge=0, le=3)
    disclosure: Literal['conceptual', 'strategy', 'scaffold']
    grade_levels: list[int]
    difficulty: Literal['general'] = 'general'
    source: str
    curriculum_source_id: Identifier
    content_version: str
    review_status: str
    approved: bool
    text_sha256: str


class PrerequisitePath(Contract):
    concept_id: Identifier
    concept_ids: list[Identifier]
    edge_ids: list[Identifier]
    depth: int = Field(ge=1, le=2)
    review_status: Literal['draft', 'human_approved']


class RetrievalRequest(Contract):
    query: str = Field(min_length=1, max_length=600)
    concept_ids: list[Identifier] = Field(min_length=1, max_length=40)
    purpose: Literal['explanation', 'hint'] = 'hint'
    hint_level: int = Field(default=1, ge=1, le=3)
    top_k: int = Field(default=3, ge=1, le=5)
    method: Literal['metadata', 'lexical', 'semantic'] = 'semantic'


class RetrievedChunk(Contract):
    chunk: KnowledgeChunk
    score: float | None = Field(default=None, allow_inf_nan=False)


class RetrievalResult(Contract):
    requested_method: Literal['metadata', 'lexical', 'semantic']
    actual_method: Literal['metadata', 'lexical', 'semantic', 'none']
    query: str
    corpus_sha256: str
    candidate_count: int
    hits: list[RetrievedChunk]
    reason: str
    fallback_reason: str | None = None
    embedding_model: str | None = None
    embedding_revision: str | None = None
    embedding_dimensions: int | None = None
    vector_store: str | None = None
    collection_id: str | None = None
    query_encoding_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    query_encoding_source: Literal['kaggle_catalog', 'http_service', 'injected'] | None = None
    mode: Literal['internal_authoring_preview', 'approved_only']


class GroundingSubmission(PilotSubmission):
    hint_level: int = Field(default=1, ge=1, le=3)
    method: Literal['metadata', 'lexical', 'semantic'] = 'semantic'


class GroundedAnalysis(Contract):
    analysis: PilotAnalysis
    graph_snapshot_id: str
    graph_provider: Literal['registry', 'neo4j', 'registry_fallback']
    graph_fallback_reason: str | None = None
    prerequisites: list[PrerequisitePath]
    retrieval: RetrievalResult
    log: dict
    mode: Literal['internal_authoring_preview'] = 'internal_authoring_preview'
    updates_student_model: Literal[False] = False
    limitations: list[str]
