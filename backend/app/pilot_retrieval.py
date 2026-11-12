"""Select Qwen/pgvector for pilot requests; legacy BGE evaluator stays unchanged."""
import os
from time import perf_counter

from app.curriculum_graph import snapshot_id
from app.local_embedding import EmbeddingUnavailable
from app.qwen_query import ENCODER, QueryService, normalized
from app.qwen_catalog import QueryCatalog
from app.curriculum import load_curriculum
from app.rag_store import PgVectorStore
from app.retrieval import candidates, corpus_hash, retrieve
from app.retrieval_contracts import RetrievalResult, RetrievedChunk


def query_provider(registry, bank=None):
    provider = os.getenv('QWEN_QUERY_PROVIDER', 'catalog')
    if provider == 'http':
        return QueryService(), 'http_service'
    if provider != 'catalog':
        raise EmbeddingUnavailable('qwen_query_provider_invalid')
    if bank is None:
        current_registry, bank = load_curriculum()
        if snapshot_id(current_registry) != snapshot_id(registry):
            raise EmbeddingUnavailable('qwen_catalog_registry_mismatch')
    return QueryCatalog(registry, bank), 'kaggle_catalog'


def retrieve_pilot(registry, chunks, request, *, authoring=False, store=None, encoder=None, allow_fallback=True):
    backend = os.getenv('PILOT_RETRIEVAL_BACKEND', 'qwen_pgvector')
    if backend == 'bge_json' or request.method != 'semantic':
        return retrieve(chunks, request, authoring=authoring, allow_fallback=allow_fallback)
    pool = candidates(chunks, request, authoring=authoring)
    common = dict(requested_method=request.method, query=request.query, corpus_sha256=corpus_hash(chunks),
                  candidate_count=len(pool), mode='internal_authoring_preview' if authoring else 'approved_only')
    if not pool:
        return RetrievalResult(**common, actual_method='none', hits=[], reason='no_eligible_content')
    try:
        if backend != 'qwen_pgvector':
            raise EmbeddingUnavailable('invalid_retrieval_backend')
        store = store or PgVectorStore(snapshot_id(registry))
        store.ready(chunks)  # Do not spend model resources if the collection is absent/stale.
        if encoder is not None:
            encode, source = encoder, 'injected'
        else:
            provider, source = query_provider(registry)
            if source == 'kaggle_catalog' and provider.spec['corpus_sha256'] != common['corpus_sha256']:
                raise EmbeddingUnavailable('qwen_catalog_corpus_mismatch')
            encode = provider.encode
        started = perf_counter()
        vector = normalized(encode(request.query))
        encode_ms = round((perf_counter() - started) * 1000, 3)
        cid, ranked = store.search(chunks, request, vector, pool, authoring=authoring)
        return RetrievalResult(**common, actual_method='semantic', reason='ranked' if ranked else 'no_eligible_content',
            hits=[RetrievedChunk(chunk=c, score=s) for c,s in ranked],
            embedding_model=ENCODER['model_id'], embedding_revision=ENCODER['revision'],
            embedding_dimensions=2560, vector_store='pgvector', collection_id=cid,
            query_encoding_ms=encode_ms, query_encoding_source=source)
    except EmbeddingUnavailable as error:
        if not allow_fallback:
            raise
        result = retrieve(chunks, request.model_copy(update={'method': 'lexical'}), authoring=authoring)
        return result.model_copy(update={'requested_method': 'semantic', 'fallback_reason': str(error),
                                         'vector_store': 'lexical_fallback'})
