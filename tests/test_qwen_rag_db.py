"""Real pgvector tests in a private retained schema; opt in, no learner data."""
import copy
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.db import connect
from app.curriculum import load_curriculum
from app.curriculum_graph import snapshot_id
from app.local_embedding import EmbeddingUnavailable
from app.qwen_query import ENCODER
from app.rag_store import migrate, sync, PgVectorStore, collection_id
from app.retrieval import corpus, candidates, corpus_hash, digest, embedding_text
from app.retrieval_contracts import RetrievalRequest

pytestmark = pytest.mark.skipif(os.getenv('RUN_RAG_DB_TESTS') != '1', reason='Requires real PostgreSQL + pgvector')

REGISTRY, BANK = load_curriculum()
CHUNKS = corpus(REGISTRY, BANK)


def vector(i):
    result = [0.] * 2560
    result[i] = 1.
    return result


VECTORS = {c.content_id: vector(i) for i,c in enumerate(CHUNKS)}


@pytest.fixture(scope='module', autouse=True)
def database():
    # Extension lives in public; data/tables live in a test-only schema. No DROP.
    name = 'test_rag_' + uuid4().hex
    previous = os.getenv('PGOPTIONS')
    with connect() as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    os.environ['PGOPTIONS'] = f'-c search_path={name},public'
    try:
        with connect() as c: migrate(c)
        yield
    finally:
        if previous is None: os.environ.pop('PGOPTIONS',None)
        else: os.environ['PGOPTIONS'] = previous


def test_sync_real_vectors_and_registry_is_idempotent():
    with connect() as c:
        first = sync(c,REGISTRY,CHUNKS,VECTORS,'synthetic-test-only')
    with connect() as c:
        second = sync(c,REGISTRY,CHUNKS,VECTORS,'synthetic-test-only')
        assert c.execute('SELECT count(*) AS n FROM rag_chunks WHERE collection_id=%s', (first['collection_id'],)).fetchone()['n'] == 40
        assert c.execute('SELECT payload FROM rag_registry_snapshots WHERE snapshot_id=%s', (snapshot_id(REGISTRY),)).fetchone()['payload'] == REGISTRY.model_dump(mode='json')
        assert c.execute('SELECT public.vector_dims(embedding) AS n FROM rag_chunks LIMIT 1').fetchone()['n'] == 2560
    assert first['inserted'] == 40 and second['inserted'] == 0


@pytest.mark.parametrize('level',[1,2,3])
def test_exact_pgvector_order_prefilter_and_hint_levels(level):
    with connect() as c: sync(c,REGISTRY,CHUNKS,VECTORS,'synthetic-test-only')
    req = RetrievalRequest(query='new query',concept_ids=['A02'],purpose='hint',hint_level=level)
    pool = candidates(CHUNKS,req,authoring=True)
    store = PgVectorStore(snapshot_id(REGISTRY))
    target = f'A02-hint-{level}'
    assert store.ready(CHUNKS) == collection_id(CHUNKS,snapshot_id(REGISTRY))
    cid, ranked = store.search(CHUNKS,req,VECTORS[target],pool,authoring=True)
    assert ranked[0][0].content_id == target and ranked[0][1] == pytest.approx(1.)
    assert len(ranked) == level and all(c.hint_level <= level for c,s in ranked)
    # Public candidates remain empty: importing a draft does not approve it.
    _, public = store.search(CHUNKS,req,VECTORS[target],candidates(CHUNKS,req),authoring=False)
    assert public == []


def test_existing_collection_cannot_be_replaced_or_silently_repaired():
    with connect() as c: sync(c,REGISTRY,CHUNKS,VECTORS,'synthetic-test-only')
    altered = copy.deepcopy(VECTORS)
    altered[CHUNKS[0].content_id] = vector(200)
    with pytest.raises(ValueError,match='differs'):
        with connect() as c: sync(c,REGISTRY,CHUNKS,altered,'synthetic-test-only')
    with pytest.raises(ValueError,match='differs'):
        with connect() as c: sync(c,REGISTRY,CHUNKS,VECTORS,'another-artifact')
    with connect() as c:
        stored = c.execute('SELECT embedding::text AS v FROM rag_chunks WHERE collection_id=%s AND content_id=%s',
            (collection_id(CHUNKS,snapshot_id(REGISTRY)),CHUNKS[0].content_id)).fetchone()['v']
    assert stored.startswith('[1,0,0,')


def test_missing_or_stale_collection_is_rejected():
    with pytest.raises(EmbeddingUnavailable,match='missing_or_stale'):
        PgVectorStore('nonexistent-registry').ready(CHUNKS)
    changed = [CHUNKS[0].model_copy(update={'approved':True}), *CHUNKS[1:]]
    with pytest.raises(EmbeddingUnavailable,match='missing_or_stale'):
        PgVectorStore(snapshot_id(REGISTRY)).ready(changed)


def test_sync_transaction_rolls_back_on_wrong_dimension():
    with connect() as c: sync(c,REGISTRY,CHUNKS,VECTORS,'synthetic-test-only')
    bad = {**VECTORS,CHUNKS[0].content_id:[1.]*1024}
    with pytest.raises(EmbeddingUnavailable):
        with connect() as c: sync(c,REGISTRY,CHUNKS,bad,'wrong-dim')
    with connect() as c:
        assert c.execute('SELECT count(*) AS n FROM rag_collections').fetchone()['n'] == 1
