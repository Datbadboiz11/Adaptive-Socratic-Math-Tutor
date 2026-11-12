"""Kaggle catalog coverage, import integrity and honest runtime provenance."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
from app import pilot_grounding, pilot_retrieval, qwen_catalog
from app.curriculum import load_curriculum
from app.grounding_queries import grounding_query
from app.local_embedding import EmbeddingUnavailable
from app.pilot_analyzer import analyze
from app.pilot_contracts import PilotSubmission
from app.qwen_query import digest, query_key
from app.retrieval import corpus
from app.retrieval_contracts import GroundingSubmission, RetrievalRequest
from research.retrieval.qwen3_4b import runtime_catalog as batch

REGISTRY, BANK = load_curriculum()
SPEC = qwen_catalog.specification(REGISTRY, BANK)
ERRORS = [(pack, error) for pack in BANK.packs for error in pack.errors]


def vector():
    return [1.] + [0.] * 2559


def document():
    return {'schema_version': '1.0.0', 'specification': copy.deepcopy(SPEC),
            'specification_sha256': digest(SPEC),
            'records': [{'query_sha256': q['query_sha256'], 'vector': vector()} for q in SPEC['queries']]}


def catalog_file(tmp_path):
    target = tmp_path / 'catalog.json'
    target.write_text(json.dumps(document(), ensure_ascii=False), encoding='utf-8')
    return target


@pytest.mark.parametrize('pack,error', ERRORS, ids=[e.error_id for p,e in ERRORS])
def test_all_authored_analyzer_diagnostics_have_exact_catalog_query(pack, error):
    problem = next(p for p in pack.problems if p.case_id == error.problem_id)
    result = analyze(problem, PilotSubmission(submission_kind='steps', steps=error.response_steps), pack.errors)
    concept = next(c for c in REGISTRY.concepts if c.concept_id == problem.concept_id)
    text = grounding_query(concept, result.diagnostic_question)
    assert result.diagnostic_question == error.diagnostic_question
    assert {'query_sha256': query_key(text), 'text': text} in SPEC['queries']


def test_catalog_covers_objectives_without_shipping_learner_or_reference_work():
    assert len(SPEC['queries']) == 30
    for pack in BANK.packs:
        concept = next(c for c in REGISTRY.concepts if c.concept_id == pack.concept_id)
        assert grounding_query(concept) in [q['text'] for q in SPEC['queries']]
    assert all(set(q) == {'query_sha256', 'text'} and len(q['text']) <= 600 for q in SPEC['queries'])
    assert SPEC == qwen_catalog.specification(REGISTRY, BANK)


@pytest.mark.parametrize('change', ['schema', 'encoder', 'corpus', 'registry', 'policy', 'text', 'hash', 'missing', 'duplicate', 'dim', 'zero', 'bool', 'nan'])
def test_invalid_stale_or_incomplete_catalog_rejected(change):
    doc = document()
    if change == 'schema': doc['schema_version'] = '99'
    elif change == 'encoder': doc['specification']['encoder']['revision'] = 'old'
    elif change in ('corpus','registry','policy'):
        key = {'corpus':'corpus_sha256','registry':'registry_snapshot_id','policy':'query_policy'}[change]
        doc['specification'][key] = 'stale'
    elif change == 'text': doc['specification']['queries'][0]['text'] += 'new'
    elif change == 'hash': doc['specification_sha256'] = 'stale'
    elif change == 'missing': doc['records'].pop()
    elif change == 'duplicate': doc['records'][1] = doc['records'][0]
    elif change == 'dim': doc['records'][0]['vector'] = [1.] * 1024
    elif change == 'zero': doc['records'][0]['vector'] = [0.] * 2560
    elif change == 'bool': doc['records'][0]['vector'][0] = True
    else: doc['records'][0]['vector'][0] = float('nan')
    with pytest.raises(EmbeddingUnavailable): qwen_catalog.validate(doc, SPEC)


def test_exact_lookup_never_reuses_vector_for_unseen_or_similar_text(tmp_path):
    provider = qwen_catalog.QueryCatalog(REGISTRY, BANK, catalog_file(tmp_path))
    text = SPEC['queries'][0]['text']
    assert provider.ready()['query_count'] == 30
    assert provider.encode(text) == vector()
    with pytest.raises(EmbeddingUnavailable, match='qwen_query_not_in_catalog'):
        provider.encode(text + ' thêm câu mới')
    with pytest.raises(EmbeddingUnavailable, match='qwen_catalog_missing'):
        qwen_catalog.QueryCatalog(REGISTRY, BANK, tmp_path/'absent.json').ready()


def test_catalog_runtime_uses_pgvector_and_labels_batch_source(tmp_path, monkeypatch):
    monkeypatch.setenv('QWEN_QUERY_PROVIDER', 'catalog')
    monkeypatch.setenv('PILOT_RETRIEVAL_BACKEND', 'qwen_pgvector')
    monkeypatch.setenv('QWEN_QUERY_CATALOG_PATH', str(catalog_file(tmp_path)))
    class Store:
        def __init__(self, *args): pass
        def ready(self, *args): return 'collection'
        def search(self, chunks, req, v, pool, **kwargs):
            assert v == vector()
            return 'collection', [(pool[0], .9)]
    monkeypatch.setattr(pilot_retrieval, 'PgVectorStore', Store)
    monkeypatch.setattr(pilot_grounding, 'analyze_bounded', analyze)
    pack = next(p for p in BANK.packs if p.concept_id == 'A02')
    problem = next(p for p in pack.problems if p.case_id == 'P-A02-01')
    result = pilot_grounding.ground(REGISTRY, BANK, pack, problem,
        GroundingSubmission(submission_kind='steps', steps=['3x+2']))
    assert result.retrieval.actual_method == 'semantic'
    assert result.retrieval.query_encoding_source == result.log['query_encoding_source'] == 'kaggle_catalog'
    assert not result.updates_student_model
    request = RetrievalRequest(query='Một câu hỏi chưa chạy trên Kaggle', concept_ids=['A02'])
    result = pilot_retrieval.retrieve_pilot(REGISTRY, corpus(REGISTRY,BANK), request, authoring=True)
    assert result.actual_method == 'lexical' and result.fallback_reason == 'qwen_query_not_in_catalog'
    assert result.query_encoding_source is None and result.embedding_model is None


def test_invalid_provider_is_explicit(monkeypatch):
    monkeypatch.setenv('QWEN_QUERY_PROVIDER', 'typo')
    with pytest.raises(EmbeddingUnavailable, match='qwen_query_provider_invalid'):
        pilot_retrieval.query_provider(REGISTRY, BANK)


def test_kaggle_input_roundtrip_and_hashes(tmp_path):
    info = batch.prepare(tmp_path/'input.zip')
    raw, spec = batch.read_input(info['archive'])
    assert spec == SPEC and len(spec['queries']) == 30
    assert 'backend/app/qwen_query.py' in raw
    assert 'corpus.json' not in raw and 'queries.json' not in raw
    raw['specification.json'] = b'{}'
    bad = tmp_path/'bad.zip'; bad.write_bytes(batch.archive(raw))
    with pytest.raises(ValueError): batch.read_input(bad)


def test_kaggle_run_export_import_without_gpu_using_stub(tmp_path, monkeypatch):
    # Fake vectors stay ONLY in pytest temp paths. This checks protocol, not model quality.
    input_path = tmp_path/'data/exports'/batch.INPUT_NAME
    batch.prepare(input_path)
    monkeypatch.setattr(batch.experiment, 'reset_peak_memory', lambda: None)
    monkeypatch.setattr(batch.experiment, 'gpu_sync', lambda: None)
    monkeypatch.setattr(batch.experiment, 'peak_memory', lambda: {'0': 1})
    monkeypatch.setattr(batch.experiment, 'load_model', lambda p: SimpleNamespace(runtime={'test_stub': True}))
    def encode(model, texts, **kwargs):
        assert texts == [q['text'] for q in SPEC['queries']]
        assert kwargs == {'queries': True, 'batch_size': 2}
        return [vector() for _ in texts]
    monkeypatch.setattr(batch.experiment, 'encode_texts', encode)
    output = tmp_path/'output.zip'
    assert batch.run(input_path, output, tmp_path/'cache')['queries'] == 30
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    target = tmp_path/'imported/catalog.json'
    assert batch.import_output(output, target)['queries'] == 30
    original = target.read_bytes()
    assert qwen_catalog.QueryCatalog(REGISTRY, BANK, target).ready()['query_count'] == 30
    assert batch.import_output(output, target)['queries'] == 30 and target.read_bytes() == original
    target.write_bytes(b'user existing content')
    with pytest.raises(ValueError, match='Catalog exists'):
        batch.import_output(output, target)
    assert target.read_bytes() == b'user existing content'


def test_notebook_input_are_paired_and_all_cells_compile(tmp_path):
    notebook = json.loads((ROOT/'research/retrieval/qwen3_4b/qwen3_runtime_queries_kaggle.ipynb').read_text(encoding='utf-8'))
    # CI does not have ignored data/ artifacts. Rebuild from tracked source.
    info = batch.prepare(tmp_path/'input.zip')
    raw, _ = batch.read_input(info['archive'])
    codes = [''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code']
    assert hashlib.sha256(raw['manifest.json']).hexdigest() in codes[0]
    for code in codes: ast.parse(code)
    # Preserve the user's successfully executed Kaggle notebook and its evidence.
    for c in notebook['cells']:
        if c['cell_type'] == 'code':
            assert c['execution_count'] is None or type(c['execution_count']) is int
            assert not any(o.get('output_type') == 'error' for o in c.get('outputs', []))
