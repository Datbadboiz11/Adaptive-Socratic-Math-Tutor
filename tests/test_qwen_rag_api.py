"""Actual HTTP contract/auth checks on platforms with ASGI TestClient support."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app import qwen_service, pilot_api
from app.main import app
from app.sessions import principal

pytestmark = pytest.mark.skipif(os.getenv('SKIP_ASGI_TESTS')=='1',reason='ASGI loopback unavailable in this Windows sandbox; run in CI')


def test_pilot_retrieval_still_requires_auth_and_both_flags(monkeypatch):
    monkeypatch.setenv('DEMO_MODE','true')
    monkeypatch.setenv('PILOT_ANALYZER_ENABLED','true')
    monkeypatch.setenv('PILOT_GROUNDING_ENABLED','true')
    with TestClient(app) as client:
        assert client.get('/api/v1/pilot/retrieval/status').status_code==401
        app.dependency_overrides[principal]=lambda:'synthetic-rag-test'
        try:
            monkeypatch.setenv('PILOT_GROUNDING_ENABLED','false')
            assert client.get('/api/v1/pilot/retrieval/status').status_code==403
            monkeypatch.setenv('PILOT_GROUNDING_ENABLED','true')
            monkeypatch.setenv('PILOT_ANALYZER_ENABLED','false')
            assert client.get('/api/v1/pilot/retrieval/status').status_code==403
            monkeypatch.setenv('PILOT_ANALYZER_ENABLED','true')
            class Missing:
                def __init__(self,*a): pass
                def ready(self,*a):
                    from app.local_embedding import EmbeddingUnavailable
                    raise EmbeddingUnavailable('pgvector_unavailable')
            monkeypatch.setattr(pilot_api,'PgVectorStore',Missing)
            monkeypatch.setenv('QWEN_SERVICE_URL','')
            result=client.get('/api/v1/pilot/retrieval/status')
            assert result.status_code==200 and not result.json()['store_ready']
            assert not result.json()['query_service_configured']
            assert 'secret' not in result.text
            result=client.post('/api/v1/pilot/retrieve',json={'query':'gợi ý','concept_ids':['A02'],'method':'metadata'})
            assert result.status_code==200 and result.json()['mode']=='internal_authoring_preview'
            assert 'reference_answer' not in result.text
        finally:
            app.dependency_overrides.clear()


def test_embedding_service_http_auth_and_new_query_binding(monkeypatch):
    token='test-model-service-token-123456789'
    monkeypatch.setenv('QWEN_SERVICE_TOKEN',token)
    monkeypatch.setenv('QWEN_MODEL_ENABLED','false')
    vector=[1.]+[0.]*2559
    with TestClient(qwen_service.app) as client:
        assert client.post('/v1/embed-query',json={'text':'câu hỏi mới'}).status_code==401
        headers={'Authorization':'Bearer '+token}
        assert client.get('/health/ready',headers=headers).status_code==503
        monkeypatch.setattr(qwen_service.app.state,'runtime',SimpleNamespace(encode=lambda _:vector,info={'precision':'float16'}))
        response=client.post('/v1/embed-query',headers=headers,json={'text':'câu hỏi mới'})
        assert response.status_code==200 and len(response.json()['vector'])==2560
        assert response.json()['query_sha256']==qwen_service.query_key('câu hỏi mới')
        assert client.post('/v1/embed-query',headers=headers,json={'text':'a','model':'other'}).status_code==422
        assert client.post('/v1/embed-query',headers=headers,json={'text':' '*5}).status_code==422
