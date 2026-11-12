"""Qwen runtime protocol, strict projection, fallback and immutable store inputs."""
import copy
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app import pilot_retrieval, pilot_grounding, qwen_query, rag_store, qwen_service
from app.curriculum import load_curriculum
from app.curriculum_graph import snapshot_id
from app.local_embedding import EmbeddingUnavailable
from app.pilot_analyzer import analyze
from app.retrieval import corpus, candidates, corpus_hash, digest, embedding_text
from app.retrieval_contracts import RetrievalRequest, GroundingSubmission

REGISTRY, BANK = load_curriculum()
CHUNKS = corpus(REGISTRY, BANK)
TOKEN = 'test-only-not-a-secret-token-123456'


def vector(i=0):
    result = [0.] * 2560
    result[i] = 1.
    return result


def request(**changes):
    return RetrievalRequest(query='Cách nhân một số với tổng trong ngoặc', concept_ids=['A02'],
                            **{'purpose': 'hint', 'method': 'semantic', 'hint_level': 1, **changes})


def index():
    return {'schema_version': '1.0.0', 'encoder': qwen_query.ENCODER,
            'corpus_sha256': corpus_hash(CHUNKS), 'records': [
                {'content_id': c.content_id, 'text_sha256': digest(embedding_text(c)), 'vector': vector(i)}
                for i,c in enumerate(CHUNKS)]}


def test_qwen_configuration_matches_verified_experiment():
    from research.retrieval.qwen3_4b import experiment
    assert qwen_query.ENCODER == experiment.ENCODER
    assert qwen_query.query_key('câu hỏi') == experiment.query_key('câu hỏi')


def test_query_service_new_text_bound_to_encoder_and_no_redirect(monkeypatch):
    seen = {}
    text = 'Làm sao phân phối hệ số vào một tổng mới?'
    def open_request(req, **kwargs):
        seen.update(url=req.full_url, body=json.loads(req.data), headers=req.headers, timeout=kwargs['timeout'])
        return io.BytesIO(json.dumps({'encoder': qwen_query.ENCODER,
            'query_sha256': qwen_query.query_key(text), 'vector': vector()}).encode())
    monkeypatch.setattr(qwen_query, 'build_opener', lambda *a: SimpleNamespace(open=open_request))
    assert qwen_query.QueryService('http://127.0.0.1:8011', TOKEN, 30).encode(text) == vector()
    assert seen['body'] == {'text': text} and seen['timeout'] == 30
    assert seen['url'].endswith('/v1/embed-query')
    assert qwen_query.NoRedirect().redirect_request(None,None,None,None,None,None) is None


@pytest.mark.parametrize('change', ['wrong_model', 'wrong_query', 'nan', 'wrong_dimensions', 'oversized', 'exception'])
def test_query_service_rejects_invalid_response_without_leaking_secrets(monkeypatch, change):
    result = {'encoder': qwen_query.ENCODER, 'query_sha256': qwen_query.query_key('new query'), 'vector': vector()}
    if change == 'wrong_model': result['encoder'] = {**qwen_query.ENCODER, 'model_id': 'BAAI/bge-m3'}
    if change == 'wrong_query': result['query_sha256'] = 'old-query'
    if change == 'nan': result['vector'][0] = float('nan')
    if change == 'wrong_dimensions': result['vector'] = [1.]*1024
    def open_request(*a, **k):
        if change == 'exception': raise RuntimeError('secret-token private-host raw-query')
        return io.BytesIO(b'x'*262145 if change == 'oversized' else json.dumps(result).encode())
    monkeypatch.setattr(qwen_query, 'build_opener', lambda *a: SimpleNamespace(open=open_request))
    with pytest.raises(EmbeddingUnavailable) as error:
        qwen_query.QueryService('http://localhost:8011', TOKEN).encode('new query')
    assert not any(s in str(error.value) for s in ['secret-token','private-host','raw-query',TOKEN])


@pytest.mark.parametrize('url', ['http://user:secret@localhost:8011','https://example.com/path',
    'http://example.com', 'file:///tmp/model', 'http://localhost?token=secret'])
def test_query_service_rejects_invalid_configuration(url):
    with pytest.raises(EmbeddingUnavailable): qwen_query.QueryService(url, TOKEN)


@pytest.mark.parametrize('change', ['model','corpus','text','duplicate','dimension','bool','zero'])
def test_store_index_refuses_incompatible_or_stale_vectors(change):
    doc = copy.deepcopy(index())
    if change == 'model': doc['encoder']['revision'] = 'wrong'
    elif change == 'corpus': doc['corpus_sha256'] = 'stale'
    elif change == 'text': doc['records'][0]['text_sha256'] = 'changed'
    elif change == 'duplicate': doc['records'][1] = doc['records'][0]
    elif change == 'dimension': doc['records'][0]['vector'] = [1.]*1024
    elif change == 'bool': doc['records'][0]['vector'][0] = True
    else: doc['records'][0]['vector'] = [0.]*2560
    with pytest.raises(EmbeddingUnavailable): rag_store.validate_index(doc, CHUNKS)


def test_approved_boundary_skips_store_and_model(monkeypatch):
    class Forbidden:
        def ready(self, *a): raise AssertionError('Drafts must never open retrieval/model')
    result = pilot_retrieval.retrieve_pilot(REGISTRY, CHUNKS, request(), store=Forbidden(),
        encoder=lambda _: pytest.fail('No model call without eligible content'))
    assert result.actual_method == 'none' and not result.hits


def test_pilot_new_query_uses_prefiltered_pgvector_and_records_identity(monkeypatch):
    seen = {}
    class Store:
        def ready(self, chunks): seen['ready'] = True
        def search(self, chunks, req, v, pool, **kwargs):
            assert seen['ready'] and v == vector()
            assert [c.content_id for c in pool] == ['A02-hint-1']
            return 'collection-test', [(pool[0], .9)]
    def encoder(text):
        seen['text'] = text
        return vector()
    result = pilot_retrieval.retrieve_pilot(REGISTRY, CHUNKS, request(), authoring=True, store=Store(), encoder=encoder)
    assert result.actual_method == 'semantic' and result.vector_store == 'pgvector'
    assert result.embedding_dimensions == 2560 and result.embedding_model == qwen_query.MODEL_ID
    assert result.collection_id == 'collection-test' and seen['text'] == request().query
    assert result.hits[0].chunk.hint_level == 1 and result.query_encoding_ms >= 0


def test_missing_store_fallback_is_explicit_and_strict_mode_raises(monkeypatch):
    class Store:
        def ready(self, chunks): raise EmbeddingUnavailable('qwen_collection_missing_or_stale')
    forbidden = lambda _: pytest.fail('Missing collection must not call a model')
    result = pilot_retrieval.retrieve_pilot(REGISTRY, CHUNKS, request(), authoring=True, store=Store(), encoder=forbidden)
    assert result.requested_method == 'semantic' and result.actual_method == 'lexical'
    assert result.fallback_reason == 'qwen_collection_missing_or_stale' and result.vector_store == 'lexical_fallback'
    assert result.embedding_model is None
    with pytest.raises(EmbeddingUnavailable):
        pilot_retrieval.retrieve_pilot(REGISTRY, CHUNKS, request(), authoring=True, store=Store(), encoder=forbidden, allow_fallback=False)


def test_service_failure_falls_back_without_claiming_semantic(monkeypatch):
    class Store:
        def ready(self, chunks): return 'ready'
    def down(_): raise EmbeddingUnavailable('qwen_service_unavailable')
    result = pilot_retrieval.retrieve_pilot(REGISTRY, CHUNKS, request(), authoring=True, store=Store(), encoder=down)
    assert result.actual_method == 'lexical' and result.fallback_reason == 'qwen_service_unavailable'


def test_grounding_uses_trusted_objective_not_raw_learner_steps(monkeypatch):
    monkeypatch.setattr(pilot_grounding, 'analyze_bounded', analyze)
    seen = {}
    original = pilot_grounding.retrieve_pilot
    def capture(registry,chunks,req,**kwargs):
        seen['query'] = req.query
        return original(registry,chunks,req.model_copy(update={'method':'metadata'}),**kwargs)
    monkeypatch.setattr(pilot_grounding, 'retrieve_pilot', capture)
    pack = next(p for p in BANK.packs if p.concept_id=='A02')
    problem = next(p for p in pack.problems if p.case_id=='P-A02-01')
    result = pilot_grounding.ground(REGISTRY,BANK,pack,problem,
        GroundingSubmission(steps=['3x+2'],submission_kind='steps'),provider='registry')
    assert result.analysis.assessment.assessment_status == 'verified_incorrect'
    assert '3x+2' not in seen['query'] and 'reference_answer' not in result.log
    assert not result.updates_student_model and result.log['vector_store'] is None


def test_model_service_token_and_busy_guard(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv('QWEN_SERVICE_TOKEN', TOKEN)
    for token in [None, 'Bearer sai', 'Bearer tiếng Việt']:
        with pytest.raises(HTTPException) as error: qwen_service.require_token(token)
        assert error.value.status_code == 401
    qwen_service.require_token('Bearer '+TOKEN)
    monkeypatch.setattr(qwen_service.app.state,'runtime',None)
    with pytest.raises(HTTPException) as error: qwen_service.encode(qwen_service.Query(text='câu mới'))
    assert error.value.status_code == 503
    runtime = SimpleNamespace(encode=lambda _: vector(),info={'precision':'float16'})
    monkeypatch.setattr(qwen_service.app.state,'runtime',runtime)
    response = qwen_service.encode(qwen_service.Query(text='câu mới'))
    assert response['query_sha256'] == qwen_query.query_key('câu mới') and response['vector']==vector()
    qwen_service._lock.acquire()
    try:
        with pytest.raises(HTTPException) as error: qwen_service.encode(qwen_service.Query(text='câu mới'))
        assert error.value.status_code == 503 and error.value.detail == 'embedding_busy'
    finally:
        qwen_service._lock.release()


def test_service_can_boot_disabled_without_download_or_torch(monkeypatch):
    monkeypatch.setenv('QWEN_MODEL_ENABLED','false')
    monkeypatch.setattr(qwen_service,'Runtime',lambda *a: pytest.fail('No implicit model loading'))
    qwen_service.initialize_runtime(qwen_service.app)
    assert qwen_service.app.state.runtime is None


@pytest.mark.parametrize('change',['hash','corpus','dimension'])
def test_artifact_validation_before_sync_never_trusts_index_alone(tmp_path,change):
    import hashlib
    payload={n:{} for n in ['index.json','corpus.json','queries.json','query-vectors.json','evaluation.json','bge-baseline.json']}
    payload['index.json']=index()
    payload['corpus.json']=[c.model_dump(mode='json') for c in CHUNKS]
    if change=='dimension': payload['index.json']['records'][0]['vector']=[1.]*1024
    if change=='corpus': payload['corpus.json'][0]['approved']=True
    for name,value in payload.items(): (tmp_path/name).write_text(json.dumps(value),encoding='utf-8')
    manifest={'schema_version':'1.0.0','encoder':qwen_query.ENCODER,'corpus_sha256':corpus_hash(CHUNKS),
              'sha256':{n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in payload}}
    (tmp_path/'run-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    if change=='hash': (tmp_path/'evaluation.json').write_text('changed',encoding='utf-8')
    with pytest.raises(EmbeddingUnavailable): rag_store.read_artifact(tmp_path,CHUNKS)


def test_cpu_runtime_loads_only_pinned_cached_fp16_weights(monkeypatch):
    calls={}
    def load_model(*a,**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(eval=lambda:None,config=SimpleNamespace(hidden_size=2560),
            parameters=lambda:iter([SimpleNamespace(dtype='fp16',is_floating_point=lambda:True)]),
            get_input_embeddings=lambda:SimpleNamespace(weight=SimpleNamespace(device='cpu')),
            hf_device_map={'':'cpu'})
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(float16='fp16',__version__='mock'))
    monkeypatch.setitem(sys.modules,'transformers',SimpleNamespace(
        AutoModel=SimpleNamespace(from_pretrained=load_model),
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a,**k:SimpleNamespace(padding_side='left'))))
    runtime=qwen_service.Runtime('cache-only','cpu')
    assert calls['local_files_only'] is True and calls['trust_remote_code'] is False
    assert calls['revision']==qwen_query.MODEL_REVISION and calls['dtype']=='fp16'
    assert calls['device_map']=={'':'cpu'} and calls['use_cache'] is False
    assert runtime.info['precision']=='float16' and runtime.info['device']=='cpu'


def test_pgvector_connection_failure_is_sanitized_before_model_use():
    def unavailable(): raise RuntimeError('postgres://user:secret@private-db/raw-query')
    store=rag_store.PgVectorStore(snapshot_id(REGISTRY),connection_factory=unavailable)
    with pytest.raises(EmbeddingUnavailable) as error: store.ready(CHUNKS)
    assert str(error.value)=='pgvector_unavailable'


def test_cache_load_error_does_not_expose_paths_or_secrets(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv('QWEN_MODEL_ENABLED','true')
    monkeypatch.setenv('QWEN_SERVICE_TOKEN',TOKEN)
    def missing(*a): raise OSError('private-path secret-token')
    monkeypatch.setattr(qwen_service,'Runtime',missing)
    qwen_service.initialize_runtime(qwen_service.app)
    with pytest.raises(HTTPException) as error: qwen_service.ready()
    assert error.value.status_code==503
    assert error.value.detail=={'code':'embedding_not_ready','reason':'model_cache_unavailable'}
    assert 'secret' not in str(error.value.detail) and 'private' not in str(error.value.detail)
