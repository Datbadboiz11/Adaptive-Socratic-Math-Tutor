"""Opt-in authenticated authoring preview. No publication, persistence or BKT."""
import os

from fastapi import APIRouter, Depends

from app.curriculum import load_curriculum
from app.pilot_analyzer import analyze_bounded
from app.pilot_contracts import PilotAnalysis, PilotProblem, PilotSubmission
from app.sessions import ApiError, principal
from app.pilot_grounding import ground
from app.retrieval import corpus, retrieve
from app.pilot_retrieval import retrieve_pilot, query_provider
from app.qwen_query import ENCODER, QueryService
from app.rag_store import PgVectorStore
from app.curriculum_graph import snapshot_id
from app.local_embedding import EmbeddingUnavailable
from app.retrieval_contracts import GroundingSubmission, GroundedAnalysis, RetrievalRequest, RetrievalResult

router = APIRouter(prefix='/api/v1/pilot', tags=['internal pilot'])


def require_preview(student=Depends(principal)):
    if os.getenv('PILOT_ANALYZER_ENABLED', 'false').lower() != 'true':
        raise ApiError(403, 'pilot_disabled', 'Chế độ kiểm tra nội dung pilot đang tắt.')
    return student


def find_problem(problem_id):
    registry, bank = load_curriculum()
    for pack in bank.packs:
        for problem in pack.problems:
            if problem.case_id == problem_id:
                return registry, pack, problem
    raise ApiError(404, 'not_found', 'Không tìm thấy bài pilot.')


def public_problem(pack, problem):
    return PilotProblem(problem_id=problem.case_id, concept_id=problem.concept_id,
        primary_skill_id=problem.primary_skill_id, content_version=pack.content_version,
        prompt=problem.prompt, task=problem.task, review_status=pack.review.status)


@router.get('/concepts')
def concepts(student=Depends(require_preview)):
    registry, bank = load_curriculum()
    names = {c.concept_id: c.title for c in registry.concepts}
    return [{'concept_id': p.concept_id, 'title': names[p.concept_id],
             'review_status': p.review.status, 'mode': 'internal_authoring_preview',
             'problems': [public_problem(p, problem).model_dump(mode='json') for problem in p.problems]}
            for p in bank.packs]


@router.get('/problems/{problem_id}', response_model=PilotProblem)
def read(problem_id: str, student=Depends(require_preview)):
    _, pack, problem = find_problem(problem_id)
    return public_problem(pack, problem)


@router.post('/problems/{problem_id}/assess', response_model=PilotAnalysis)
def assess(problem_id: str, body: PilotSubmission, student=Depends(require_preview)):
    _, pack, problem = find_problem(problem_id)
    return analyze_bounded(problem, body, pack.errors, content_version=pack.content_version)


def require_grounding(student=Depends(require_preview)):
    if os.getenv('PILOT_GROUNDING_ENABLED', 'false').lower() != 'true':
        raise ApiError(403, 'grounding_disabled', 'Chế độ kiểm tra KG/RAG pilot đang tắt.')
    return student


@router.get('/retrieval/status')
def retrieval_status(student=Depends(require_grounding)):
    registry, bank = load_curriculum()
    result = {'backend': os.getenv('PILOT_RETRIEVAL_BACKEND', 'qwen_pgvector'),
              'encoder': ENCODER, 'collection_id': None, 'store_ready': False,
              'query_service_configured': False, 'mode': 'internal_authoring_preview',
              'query_provider': os.getenv('QWEN_QUERY_PROVIDER', 'catalog'), 'query_catalog_ready': False,
              'note': 'Catalog supports exact trusted queries only; HTTP configured does not mean reachable/ready.'}
    try:
        result['collection_id'] = PgVectorStore(snapshot_id(registry)).ready(corpus(registry,bank))
        result['store_ready'] = True
    except EmbeddingUnavailable as error:
        result['store_reason'] = str(error)
    try:
        QueryService()
        result['query_service_configured'] = True
    except EmbeddingUnavailable as error:
        result['query_service_reason'] = str(error)
    try:
        provider, source = query_provider(registry, bank)
        if source == 'kaggle_catalog':
            result['query_catalog'] = provider.ready()
            result['query_catalog_ready'] = True
    except EmbeddingUnavailable as error:
        result['query_provider_reason'] = str(error)
    return result


@router.post('/retrieve', response_model=RetrievalResult)
def retrieval_preview(body: RetrievalRequest, student=Depends(require_grounding)):
    registry, bank = load_curriculum()
    valid = {c.concept_id for c in registry.concepts}
    if not set(body.concept_ids) <= valid:
        raise ApiError(422, 'unknown_concept', 'Concept ngoài registry hiện tại.')
    return retrieve_pilot(registry, corpus(registry,bank), body, authoring=True)


@router.post('/problems/{problem_id}/ground', response_model=GroundedAnalysis)
def grounding_preview(problem_id: str, body: GroundingSubmission, student=Depends(require_grounding)):
    registry, pack, problem = find_problem(problem_id)
    _, bank = load_curriculum()
    return ground(registry,bank,pack,problem,body)
