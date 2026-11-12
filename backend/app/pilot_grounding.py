"""Analyzer -> prerequisite candidates -> permitted retrieval, without generation."""
from time import perf_counter
from uuid import uuid4
from app.curriculum_graph import prerequisites, snapshot_id
from app.pilot_analyzer import analyze_bounded
from app.grounding_queries import grounding_query
from app.pilot_contracts import PilotSubmission
from app.retrieval import corpus, corpus_hash, retrieve
from app.pilot_retrieval import retrieve_pilot
from app.retrieval_contracts import GroundedAnalysis, GroundingSubmission, RetrievalRequest, RetrievalResult


def ground(registry, bank, pack, problem, body: GroundingSubmission, *, provider=None, index_path=None, query_encoder=None):
    started = perf_counter()
    submission = PilotSubmission(submission_kind=body.submission_kind, steps=body.steps)
    analysis = analyze_bounded(problem, submission, pack.errors, content_version=pack.content_version)
    routes, graph_provider, graph_fallback = prerequisites(registry, problem.concept_id, authoring=True, provider=provider)
    concept = next(c for c in registry.concepts if c.concept_id == problem.concept_id)
    # Trusted teaching objective + audited diagnostic question. Raw learner steps/answers never enter the embedding query.
    query = grounding_query(concept, analysis.diagnostic_question)
    eligible_ids = sorted({problem.concept_id, *[p.concept_id for p in routes]})
    request = RetrievalRequest(query=query[:600], concept_ids=eligible_ids, hint_level=body.hint_level,
                               purpose='hint', top_k=3, method=body.method)
    chunks = corpus(registry, bank)
    if analysis.completed or analysis.assessment.assessment_status == 'needs_clarification':
        result = RetrievalResult(requested_method=body.method, actual_method='none', query=query[:600],
            corpus_sha256=corpus_hash(chunks), candidate_count=0, hits=[],
            reason='no_support_required' if analysis.completed else 'await_clarification', mode='internal_authoring_preview')
    else:
        if index_path is not None or query_encoder is not None:
            # Explicit legacy injection remains for research baselines and existing tools.
            result = retrieve(chunks, request, authoring=True, index_path=index_path, query_encoder=query_encoder)
        else:
            result = retrieve_pilot(registry, chunks, request, authoring=True)
    log = {'trace_id':str(uuid4()), 'problem_id':problem.case_id, 'assessment_id':str(analysis.assessment.assessment_id),
           'error_evidence':analysis.assessment.evidence, 'content_version':bank.content_version,
           'source_content_ids':[h.chunk.content_id for h in result.hits],
           'edge_paths':[p.edge_ids for p in routes], 'graph_provider':graph_provider,
           'requested_retrieval':body.method, 'actual_retrieval':result.actual_method,
           'corpus_sha256':result.corpus_sha256, 'embedding_revision':result.embedding_revision,
           'embedding_model':result.embedding_model, 'embedding_dimensions':result.embedding_dimensions,
           'vector_store':result.vector_store, 'collection_id':result.collection_id,
           'query_encoding_ms':result.query_encoding_ms, 'retrieval_fallback_reason':result.fallback_reason,
           'query_encoding_source':result.query_encoding_source,
           'elapsed_ms':round((perf_counter()-started)*1000,2),
           'rationale':'Candidates from the task concept and up to two prerequisite levels; review/purpose/disclosure filtered before ranking.'}
    return GroundedAnalysis(analysis=analysis, graph_snapshot_id=snapshot_id(registry), graph_provider=graph_provider,
        graph_fallback_reason=graph_fallback, prerequisites=routes, retrieval=result, log=log,
        limitations=['Internal draft preview, not published learner content.',
                     'Graph candidates do not establish a learner deficit; retrieval scores are not confidence in a misconception.',
                     'No pedagogical action, reply generation, persistent session or BKT update in this endpoint.',
                     'Hint disclosure metadata is a boundary, not proof of pedagogical safety; human review remains required.'])
