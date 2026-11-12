"""Isolated Qwen experiment, baseline parity and no changes to BGE artifacts."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from contextlib import nullcontext
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT))
from app import retrieval, local_embedding
from app.curriculum import load_curriculum
from research.retrieval.evaluate import evaluate as bge_evaluate
from research.retrieval.qwen3_4b import experiment as exp

REGISTRY, BANK = load_curriculum()
CHUNKS = retrieval.corpus(REGISTRY, BANK)
DATASET = json.loads((ROOT / 'content/curriculum/retrieval.dev.v1.json').read_text(encoding='utf-8'))


def vector(i, dimensions=2560):
    result = [0.] * dimensions
    result[i % dimensions] = 1.
    return result


@pytest.fixture
def docs():
    bge_docs = {'corpus.json': [c.model_dump(mode='json') for c in CHUNKS], 'queries.json': DATASET}
    baseline = bge_evaluate(Path('.'), documents=bge_docs)
    # Baseline semantic scores are synthetic here, not a GPU benchmark.
    baseline['semantic_run'] = True
    baseline['methods']['semantic'] = copy.deepcopy(baseline['methods']['lexical'])
    return {'corpus.json': bge_docs['corpus.json'], 'queries.json': DATASET,
            'bge-baseline.json': {'query_set_sha256': retrieval.digest(DATASET), 'evaluation': baseline},
            'index.json': exp.build_index(CHUNKS, [vector(i) for i in range(40)]),
            'query-vectors.json': exp.query_document(DATASET['queries'], [vector(i % 40) for i in range(90)])}


def make_artifact(tmp_path, documents):
    work = tmp_path / 'artifact-work'
    work.mkdir()
    for name in exp.ARTIFACT_FILES:
        (work / name).write_bytes(exp.json_bytes(documents[name]))
    path = tmp_path / exp.OUTPUT_NAME
    exp.export_artifact(work, path, {'gpu': 'FAKE structural test'}, {}, 'test-only')
    return path


def test_baseline_parity_filtering_metrics_and_no_global_encoder_change(docs):
    before = copy.deepcopy(local_embedding.ENCODER)
    report = exp.evaluate(docs)
    baseline = docs['bge-baseline.json']['evaluation']
    assert report['methods']['metadata'] == baseline['methods']['metadata']
    assert report['methods']['lexical'] == baseline['methods']['lexical']
    strip = lambda rows: [{k: v for k, v in r.items() if k != 'ranking_ms'} for r in rows]
    assert strip([r for r in report['records'] if r['method'] != 'semantic']) == strip(baseline['records'])
    assert exp.comparison(docs, report)['Qwen3-Embedding-4B'] == report['methods']['semantic']
    rows = {q['query_id']: q for q in DATASET['queries']}
    for record in report['records']:
        request = retrieval.RetrievalRequest.model_validate(rows[record['query_id']]['request'])
        allowed = {c.content_id for c in retrieval.candidates(CHUNKS, request, authoring=True)}
        assert set(record['retrieved_ids']) <= allowed
    assert report['methods']['semantic']['positive_queries'] == 80
    assert report['methods']['semantic']['empty_results_correct'] == 10
    assert local_embedding.ENCODER == retrieval.ENCODER == before


def install_loader_fakes(monkeypatch, *, count=2, free_gib=14, dtype='fp16', offload=False):
    seen = {}
    class FakeOOM(RuntimeError): pass
    cuda = SimpleNamespace(is_available=lambda: count > 0, device_count=lambda: count,
        get_device_name=lambda i: f'T4-{i}', mem_get_info=lambda i: (free_gib*1024**3, 16*1024**3),
        empty_cache=lambda: None, OutOfMemoryError=FakeOOM)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(float16='fp16', cuda=cuda))
    def load_backbone(*args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(config=SimpleNamespace(hidden_size=2560), eval=lambda: None,
            parameters=lambda: iter([SimpleNamespace(dtype=dtype, is_floating_point=lambda: True)]),
            hf_device_map={'embed_tokens': 0, 'layers.35': 'cpu' if offload else count-1},
            get_input_embeddings=lambda: SimpleNamespace(weight=SimpleNamespace(device='cuda:0')))
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(
        AutoModel=SimpleNamespace(from_pretrained=load_backbone),
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a, **k: SimpleNamespace(padding_side=k['padding_side']))))
    return seen


@pytest.mark.parametrize('count', [1, 2])
def test_model_loads_direct_fp16_without_collapsing_multi_gpu(monkeypatch, tmp_path, count):
    seen = install_loader_fakes(monkeypatch, count=count)
    model = exp.load_model(tmp_path)
    assert seen['revision'] == exp.MODEL_REVISION and len(exp.MODEL_REVISION) == 40
    assert seen['dtype'] == 'fp16' and 'torch_dtype' not in seen
    assert seen['attn_implementation'] == 'sdpa' and seen['use_cache'] is False
    assert seen['device_map'] == ('balanced' if count==2 else {'': 0})
    assert seen['max_memory'] == {**{i:12*1024**3 for i in range(count)}, 'cpu': 0}
    assert seen['trust_remote_code'] is False and model.tokenizer.padding_side == 'left'
    assert model.runtime['precision_verified'] == 'float16'
    assert len(model.runtime['gpu_memory_before_load']) == count


@pytest.mark.parametrize('failure', ['busy', 'no_gpu', 'fp32', 'offload'])
def test_loader_rejects_busy_gpu_wrong_dtype_and_offload(monkeypatch, tmp_path, failure):
    seen = install_loader_fakes(monkeypatch, count=0 if failure=='no_gpu' else 2,
        free_gib=3 if failure=='busy' else 14, dtype='fp32' if failure=='fp32' else 'fp16',
        offload=failure=='offload')
    with pytest.raises((RuntimeError, ValueError)):
        exp.load_model(tmp_path)
    if failure in ('busy', 'no_gpu'): assert not seen


def test_instruction_last_token_pooling_and_no_silent_truncation(monkeypatch):
    import math
    tokenized, batches = [], []
    class Tensor:
        def __init__(self, values): self.values=values
        @property
        def shape(self):
            def shape(v): return (len(v), *shape(v[0])) if isinstance(v,list) else ()
            return shape(self.values)
        def __getitem__(self, key):
            def select(values, axes):
                if not axes: return values
                head, *rest=axes
                if isinstance(head,slice): return [select(v,rest) for v in values[head]]
                return select(values[head],rest)
            return Tensor(select(self.values,list(key) if isinstance(key,tuple) else [key]))
        def all(self):
            def all_values(v): return all(all_values(x) for x in v) if isinstance(v,list) else bool(v)
            return Tensor(all_values(self.values))
        def item(self): return self.values
        def float(self): return self
        def cpu(self): return self
        def tolist(self): return self.values
    class Batch(dict):
        def to(self, device):
            assert device=='cuda:0'
            return self
    def tokenize_one(text, **kwargs):
        tokenized.append(text)
        return list(range(513 if 'too-long' in text else 5))
    def tokenize_batch(texts, **kwargs):
        batches.append(texts)
        return Batch(input_ids=Tensor([[1,1,1] for _ in texts]),
                     attention_mask=Tensor([[0,1,1] for _ in texts]))
    def forward(**kwargs):
        assert kwargs['use_cache'] is False and kwargs['return_dict'] is True
        values=[[[0.]*2560 for _ in range(3)] for _ in range(kwargs['input_ids'].shape[0])]
        for row in values:
            row[0][0]=8 # Would contaminate mean/first-token pooling.
            row[-1][1]=3
            row[-1][2]=4
        return SimpleNamespace(last_hidden_state=Tensor(values))
    tokenizer=type('Tokenizer',(),{'encode':staticmethod(tokenize_one), '__call__':staticmethod(tokenize_batch)})()
    model=exp.QwenEncoder(forward,tokenizer,'cuda:0',{})
    functional=SimpleNamespace(normalize=lambda x,**k: Tensor([[v/math.sqrt(sum(t*t for t in row)) for v in row] for row in x.values]))
    nn=SimpleNamespace(functional=functional)
    torch=SimpleNamespace(inference_mode=nullcontext, nn=nn,
                          isfinite=lambda t: Tensor([[math.isfinite(v) for v in row] for row in t.values]))
    monkeypatch.setitem(sys.modules,'torch',torch)
    monkeypatch.setitem(sys.modules,'torch.nn',nn)
    monkeypatch.setitem(sys.modules,'torch.nn.functional',functional)
    rows=exp.encode_texts(model,['câu hỏi','câu hai','câu ba'],queries=True,batch_size=2)
    exp.encode_texts(model,['nội dung'])
    assert tokenized[0]==exp.ENCODER['query_prefix']+'câu hỏi' and tokenized[-1]=='nội dung'
    assert [len(b) for b in batches]==[2,1,1]
    assert rows[0][0]==0 and rows[0][1:3]==pytest.approx([.6,.8])
    with pytest.raises(ValueError,match='too long'):
        exp.encode_texts(model,['too-long'],queries=True)
    assert len(batches)==3


@pytest.mark.parametrize('change', ['dimension', 'duplicate', 'revision', 'instruction', 'nan'])
def test_reject_wrong_vectors_encoder_and_query_text(docs, change):
    docs = copy.deepcopy(docs)
    if change == 'dimension': docs['index.json']['records'][0]['vector'] = vector(0, 1024)
    elif change == 'duplicate': docs['query-vectors.json']['records'][-1] = docs['query-vectors.json']['records'][0]
    elif change == 'revision': docs['index.json']['encoder'] = {**exp.ENCODER, 'revision': 'wrong'}
    elif change == 'instruction': docs['query-vectors.json']['records'][0]['query_sha256'] = 'stale'
    else: docs['index.json']['records'][0]['vector'][0] = float('nan')
    with pytest.raises(ValueError): exp.evaluate(docs)


@pytest.mark.parametrize('layout', ['zip', 'extracted'])
def test_notebook_background_mock_roundtrip_and_old_files_untouched(tmp_path, monkeypatch, layout):
    protected = [ROOT / 'research/retrieval/bge_m3_colab.ipynb', ROOT / 'backend/app/local_embedding.py',
                 ROOT / 'backend/app/retrieval.py', ROOT / 'data/exports/pilot-retrieval-input.zip',
                 *[p for p in (ROOT / 'data/retrieval/bge-m3-v1').glob('*') if p.is_file()]]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    prepared = exp.prepare(tmp_path / exp.INPUT_NAME)
    input_root = tmp_path / 'input'
    attached = input_root / 'datasets/team/qwen/versions/1'
    attached.mkdir(parents=True)
    if layout == 'zip':
        (attached / exp.INPUT_NAME).write_bytes(Path(prepared['archive']).read_bytes())
    else:
        with ZipFile(prepared['archive']) as bundle:
            for name in bundle.namelist():
                target = attached / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(name))
    # A separately attached BGE dataset must not be selected as Qwen input.
    old = input_root / 'bge'
    old.mkdir()
    (old / 'manifest.json').write_text('{"experiment":"bge"}', encoding='utf-8')
    work_root = tmp_path / 'working'
    n = json.loads((ROOT / 'research/retrieval/qwen3_4b/qwen3_4b_kaggle.ipynb').read_text(encoding='utf-8'))
    assert len({c['id'] for c in n['cells']}) == len(n['cells'])
    cells = [''.join(c['source']) for c in n['cells'] if c['cell_type'] == 'code']
    for cell in cells: compile(cell, 'qwen-notebook', 'exec')
    first = cells[0].replace("Path('/kaggle/input')", f'Path({str(input_root)!r})')
    first = first.replace("Path('/kaggle/working')", f'Path({str(work_root)!r})')
    first = first.replace("Path('/kaggle/temp')", f'Path({str(tmp_path / "cache")!r})')
    ns = {}
    exec(first, ns)
    # Input validation must agree with the helper; no Colab UI import is possible.
    helper_raw, helper_manifest = exp.read_input(attached if layout == 'extracted' else attached / exp.INPUT_NAME)
    assert ns['raw'] == helper_raw and ns['manifest'] == helper_manifest
    monkeypatch.setitem(sys.modules, 'google.colab', None)
    class FakeOOM(RuntimeError): pass
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(__version__='mock', version=SimpleNamespace(cuda='mock'),
        cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda _: 'FAKE T4', device_count=lambda: 2,
            synchronize=lambda *a: None, reset_peak_memory_stats=lambda *a: None, max_memory_allocated=lambda *a: 0,
            mem_get_info=lambda i: (14*1024**3,16*1024**3),
            OutOfMemoryError=FakeOOM, empty_cache=lambda: None)))
    monkeypatch.setattr(exp, 'load_model', lambda cache: SimpleNamespace(runtime={'precision_verified':'float16','device_map':{'embed_tokens':'0','layers.35':'1'}}))
    seen_batches = []
    def fake_encode(model, texts, **kwargs):
        seen_batches.append(kwargs['batch_size'])
        if len(seen_batches) == 1: raise FakeOOM('structural OOM retry')
        return [vector(i % 40) for i in range(len(texts))]
    monkeypatch.setattr(exp, 'encode_texts', fake_encode)
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, 'version', lambda _: 'mock')
    for cell in cells[2:]: exec(cell, ns)  # Skip only actual pip installation.
    assert seen_batches[:2] == [2, 1]
    assert ns['timings']['corpus_encode_seconds_batch_size'] == 1
    assert ns['timings']['peak_gpu_memory_mib_by_device'] == {'0': 0, '1': 0}
    load_cell = next(c for c in cells if 'model = load_model' in c)
    with pytest.raises(RuntimeError, match='session'):
        exec(load_cell, ns)
    result_zip = work_root / exp.OUTPUT_NAME
    with ZipFile(result_zip) as bundle:
        assert set(bundle.namelist()) == set(exp.ARTIFACT_FILES + ['run-manifest.json'])
    monkeypatch.setattr(exp, 'ROOT', tmp_path)
    (tmp_path / 'content/curriculum').mkdir(parents=True)
    (tmp_path / 'content/curriculum/retrieval.dev.v1.json').write_bytes(exp.json_bytes(DATASET))
    output = tmp_path / 'data/retrieval/qwen3-4b-v1'
    assert exp.import_artifact(result_zip, output)['chunks'] == 40
    assert exp.import_artifact(result_zip, output)['chunks'] == 40
    (output / 'index.json').write_text('user change', encoding='utf-8')
    with pytest.raises(ValueError, match='Existing'): exp.import_artifact(result_zip, output)
    assert (output / 'index.json').read_text() == 'user change'
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}


@pytest.mark.parametrize('change', ['report', 'model', 'query', 'baseline'])
def test_import_checks_everything_before_writing(tmp_path, monkeypatch, docs, change):
    docs = copy.deepcopy(docs)
    docs['evaluation.json'] = exp.evaluate(docs)
    if change == 'report': docs['evaluation.json']['methods']['semantic']['hit_at_3'] = 1.5
    elif change == 'model': docs['index.json']['encoder'] = {**exp.ENCODER, 'model_id': 'BAAI/bge-m3'}
    elif change == 'query': docs['query-vectors.json']['records'][0]['query_sha256'] = 'changed'
    else: docs['bge-baseline.json']['query_set_sha256'] = 'other-query-set'
    archive = make_artifact(tmp_path, docs)
    monkeypatch.setattr(exp, 'ROOT', tmp_path)
    (tmp_path / 'content/curriculum').mkdir(parents=True)
    (tmp_path / 'content/curriculum/retrieval.dev.v1.json').write_bytes(exp.json_bytes(DATASET))
    output = tmp_path / 'data/retrieval/qwen3-4b-v1'
    with pytest.raises(ValueError): exp.import_artifact(archive, output)
    assert not output.exists()


def test_import_cannot_write_into_bge_or_outside_retrieval(tmp_path, monkeypatch):
    monkeypatch.setattr(exp, 'ROOT', tmp_path)
    for target in [tmp_path / 'data/retrieval/bge-m3-v1', tmp_path / 'elsewhere/qwen3-4b-v1']:
        with pytest.raises(ValueError, match='qwen3-4b-'):
            exp.import_artifact(tmp_path / 'missing.zip', target)
        assert not target.exists()


def test_stale_input_is_rejected_before_model_load(tmp_path):
    prepared = exp.prepare(tmp_path / exp.INPUT_NAME)
    with ZipFile(prepared['archive']) as bundle:
        raw = {name: bundle.read(name) for name in bundle.namelist()}
    name = exp.PREFIX + 'manifest.json'
    manifest = json.loads(raw[name])
    manifest.pop('runtime_loader')
    raw[name] = exp.json_bytes(manifest)
    stale = tmp_path / 'stale-input.zip'
    with ZipFile(stale, 'w') as bundle:
        for name, value in raw.items(): bundle.writestr(name, value)
    with pytest.raises(ValueError, match='configuration'):
        exp.read_input(stale)
