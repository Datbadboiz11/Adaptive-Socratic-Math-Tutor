"""Isolated Qwen3-Embedding-4B experiment; never changes the BGE runtime."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from time import perf_counter
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT))
from app.retrieval import corpus, corpus_hash, embedding_text, candidates, digest, retrieve
from app.retrieval_contracts import RetrievalRequest
from research.retrieval.evaluate import load_inputs

MODEL_ID = 'Qwen/Qwen3-Embedding-4B'
MODEL_REVISION = '5cf2132abc99cad020ac570b19d031efec650f2b'
LOADER_VERSION = 'transformers-fp16-balanced-v2'
TASK = ('Given a Vietnamese math learning question, retrieve relevant explanations or hints '
        'addressing the mathematical concept and the requested level of support.')
ENCODER = dict(model_id=MODEL_ID, revision=MODEL_REVISION, dimensions=2560,
               max_length=512, pooling='last_token', normalize=True,
               query_prefix=f'Instruct: {TASK}\nQuery:', passage_prefix='')
INPUT_NAME = 'pilot-retrieval-qwen3-4b-input.zip'
OUTPUT_NAME = 'pilot-retrieval-qwen3-4b.zip'
PREFIX = 'pilot-retrieval-qwen3-4b/'
CODE_FILES = [
    'backend/app/__init__.py', 'backend/app/contracts.py', 'backend/app/curriculum.py',
    'backend/app/pilot_contracts.py', 'backend/app/retrieval_contracts.py',
    'backend/app/retrieval.py', 'backend/app/local_embedding.py',
    'research/retrieval/evaluate.py', 'research/retrieval/requirements.txt',
    'research/retrieval/qwen3_4b/experiment.py',
    'research/retrieval/qwen3_4b/requirements.txt',
]
INPUT_FILES = CODE_FILES + ['corpus.json', 'queries.json', 'bge-baseline.json', 'manifest.json']
ARTIFACT_FILES = ['index.json', 'query-vectors.json', 'evaluation.json',
                  'corpus.json', 'queries.json', 'bge-baseline.json']


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def prepare(output=None):
    """Read existing content/baseline; write only a separate Qwen ZIP."""
    from app.curriculum import load_curriculum
    registry, bank = load_curriculum()
    chunks = corpus(registry, bank)
    queries = json.loads((ROOT / 'content/curriculum/retrieval.dev.v1.json').read_text(encoding='utf-8'))
    baseline = json.loads((ROOT / 'data/retrieval/bge-m3-v1/evaluation.json').read_text(encoding='utf-8'))
    baseline_queries = json.loads((ROOT / 'data/retrieval/bge-m3-v1/queries.json').read_text(encoding='utf-8'))
    if baseline['corpus_sha256'] != corpus_hash(chunks) or baseline_queries != queries or not baseline['semantic_run']:
        raise ValueError('BGE baseline does not match current corpus/queries')
    raw = {name: (ROOT / name).read_bytes() for name in CODE_FILES}
    raw.update({'corpus.json': json_bytes([c.model_dump(mode='json') for c in chunks]),
                'queries.json': json_bytes(queries),
                'bge-baseline.json': json_bytes({'query_set_sha256': digest(queries), 'evaluation': baseline})})
    manifest = {'schema_version': '1.0.0', 'experiment': 'qwen3-4b-v1',
                'runtime_loader': LOADER_VERSION,
                'encoder': ENCODER, 'corpus_sha256': corpus_hash(chunks),
                'query_set_sha256': digest(queries),
                'purpose': 'Internal teaching-only development comparison; no student data or reference answers',
                'sha256': {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}}
    raw['manifest.json'] = json_bytes(manifest)
    output = Path(output or ROOT / 'data/exports' / INPUT_NAME)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as bundle:
        for name, value in raw.items():
            bundle.writestr(PREFIX + name, value)
    return {'archive': str(output), 'files': len(raw), 'chunks': len(chunks),
            'queries': len(queries['queries']), 'encoder': ENCODER}


def read_input(source):
    """Support Kaggle ZIP or auto-extracted directory, validate before executing code."""
    source = Path(source)
    limit = 5 * 1024 * 1024
    if source.is_file():
        if source.stat().st_size > limit:
            raise ValueError('Input ZIP too large')
        with ZipFile(source) as bundle:
            expected = {PREFIX + name for name in INPUT_FILES}
            if set(bundle.namelist()) != expected or len(bundle.namelist()) != len(expected):
                raise ValueError('Input ZIP file allowlist mismatch')
            if sum(i.file_size for i in bundle.infolist()) > limit:
                raise ValueError('Input contents too large')
            raw = {name: bundle.read(PREFIX + name) for name in INPUT_FILES}
    else:
        if not (source / 'manifest.json').is_file() and (source / PREFIX / 'manifest.json').is_file():
            source = source / PREFIX
        if not source.is_dir() or {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} != set(INPUT_FILES):
            raise ValueError('Input directory file allowlist mismatch')
        if sum((source / name).stat().st_size for name in INPUT_FILES) > limit:
            raise ValueError('Input contents too large')
        raw = {name: (source / name).read_bytes() for name in INPUT_FILES}
    manifest = json.loads(raw['manifest.json'])
    if (manifest.get('encoder') != ENCODER or manifest.get('schema_version') != '1.0.0'
            or manifest.get('runtime_loader') != LOADER_VERSION):
        raise ValueError('Wrong Qwen experiment configuration')
    expected_hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items() if name != 'manifest.json'}
    if manifest.get('sha256') != expected_hashes:
        raise ValueError('Input SHA256 mismatch')
    return raw, manifest


def gpu_memory():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('Kaggle Settings: select GPU before Save & Run All')
    return [{'device': i, 'name': torch.cuda.get_device_name(i),
             'free_bytes': int(torch.cuda.mem_get_info(i)[0]),
             'total_bytes': int(torch.cuda.mem_get_info(i)[1])}
            for i in range(torch.cuda.device_count())]


def gpu_sync():
    import torch
    for i in range(torch.cuda.device_count()):
        torch.cuda.synchronize(i)


def reset_peak_memory():
    import torch
    for i in range(torch.cuda.device_count()):
        torch.cuda.reset_peak_memory_stats(i)


def peak_memory():
    import torch
    return {str(i): round(torch.cuda.max_memory_allocated(i) / 1024**2, 1)
            for i in range(torch.cuda.device_count())}


def load_model(cache_folder):
    """Load FP16 directly with Accelerate; never collapse a sharded model via .to()."""
    import gc
    import torch
    from transformers import AutoModel, AutoTokenizer
    gc.collect()
    torch.cuda.empty_cache()
    memory = gpu_memory()
    # Reserve activations/runtime headroom on each GPU; do not silently CPU/disk offload.
    gib = 1024**3
    budgets = {g['device']: g['free_bytes'] - 2 * gib for g in memory
               if g['free_bytes'] >= 4 * gib}
    if sum(budgets.values()) < 9 * gib:
        raise RuntimeError('Not enough free VRAM for Qwen FP16. Restart the Kaggle session '
                           '(not just rerun the cell), select T4 x2 and Run All. '
                           f'GPU memory before load: {memory}')
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION,
        cache_dir=str(cache_folder), trust_remote_code=False, padding_side='left')
    if tokenizer.padding_side != 'left':
        raise ValueError('Qwen requires left padding in this experiment')
    try:
        backbone = AutoModel.from_pretrained(MODEL_ID, revision=MODEL_REVISION,
            cache_dir=str(cache_folder), trust_remote_code=False,
            dtype=torch.float16, attn_implementation='sdpa', use_cache=False,
            use_safetensors=True,
            device_map='balanced' if len(budgets) > 1 else {'': next(iter(budgets))},
            max_memory={**budgets, 'cpu': 0})
    except torch.cuda.OutOfMemoryError as error:
        raise RuntimeError('Qwen ran out of VRAM during loading. Restart the Kaggle session '
                           'and Run All with the updated input ZIP; reducing encode batch '
                           'cannot fix a model-load OOM.') from error
    backbone.eval()
    if backbone.config.hidden_size != ENCODER['dimensions']:
        raise ValueError('Unexpected Qwen output dimension')
    if any(p.dtype != torch.float16 for p in backbone.parameters() if p.is_floating_point()):
        raise ValueError('Qwen weights are not all FP16; refusing an ambiguous run')
    placement = getattr(backbone, 'hf_device_map', {})
    if not placement or any(str(v) in ('cpu', 'disk', 'meta') for v in placement.values()):
        raise ValueError('Qwen is not fully on GPU; CPU/disk offload is not enabled')
    input_device = backbone.get_input_embeddings().weight.device
    runtime = {'runtime_loader': LOADER_VERSION, 'device_map': {k: str(v) for k, v in placement.items()},
               'input_device': str(input_device), 'precision_verified': 'float16',
               'gpu_memory_before_load': memory, 'gpu_memory_after_load': gpu_memory()}
    return QwenEncoder(backbone, tokenizer, input_device, runtime)


class QwenEncoder:
    def __init__(self, backbone, tokenizer, input_device, runtime):
        self.backbone, self.tokenizer = backbone, tokenizer
        self.input_device, self.runtime = input_device, runtime


def normalized(vector):
    if not isinstance(vector, list) or len(vector) != ENCODER['dimensions'] or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in vector):
        raise ValueError('Invalid Qwen vector')
    norm = math.sqrt(sum(v * v for v in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError('Invalid Qwen vector norm')
    return [v / norm for v in vector]


def encode_texts(model, texts, *, queries=False, batch_size=2):
    if not 1 <= batch_size <= 8 or not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
        raise ValueError('Invalid encode input/batch')
    prompt = ENCODER['query_prefix'] if queries else ENCODER['passage_prefix']
    if any(len(model.tokenizer.encode(prompt + t, add_special_tokens=True)) > ENCODER['max_length'] for t in texts):
        raise ValueError('Input too long; refusing silent truncation (including instruction/EOS)')
    import torch
    import torch.nn.functional as functional
    rows = []
    with torch.inference_mode():
        for offset in range(0, len(texts), batch_size):
            batch = model.tokenizer([prompt + t for t in texts[offset:offset + batch_size]],
                padding=True, truncation=False, return_tensors='pt')
            if batch['input_ids'].shape[1] > ENCODER['max_length']:
                raise ValueError('Input too long; refusing silent truncation')
            # Left padding plus the pinned tokenizer/EOS makes the last position valid.
            if not batch['attention_mask'][:, -1].all().item():
                raise ValueError('Unexpected right padding or empty input')
            batch = batch.to(model.input_device)
            result = model.backbone(**batch, use_cache=False, return_dict=True)
            pooled = result.last_hidden_state[:, -1, :].float()
            if not torch.isfinite(pooled).all().item():
                raise ValueError('Non-finite Qwen hidden state')
            rows.extend(functional.normalize(pooled, p=2, dim=1).cpu().tolist())
            del result, pooled, batch
    if len(rows) != len(texts):
        raise ValueError('Vector count mismatch')
    return [normalized(row) for row in rows]


def build_index(chunks, vectors, environment=None):
    if len(chunks) != len(vectors):
        raise ValueError('Corpus vector count mismatch')
    return {'schema_version': '1.0.0', 'encoder': ENCODER, 'corpus_sha256': corpus_hash(chunks),
            'environment': environment or {}, 'records': [
                {'content_id': c.content_id, 'text_sha256': digest(embedding_text(c)), 'vector': normalized(v)}
                for c, v in zip(chunks, vectors)]}


def query_key(text):
    return digest({'encoder': ENCODER, 'query': text})


def query_document(queries, vectors):
    if len(queries) != len(vectors):
        raise ValueError('Query vector count mismatch')
    return {'encoder': ENCODER, 'records': [
        {'query_id': q['query_id'], 'query_sha256': query_key(q['request']['query']), 'vector': normalized(v)}
        for q, v in zip(queries, vectors)]}


def validate_vectors(documents, chunks, dataset):
    index = documents['index.json']
    if index.get('encoder') != ENCODER or index.get('schema_version') != '1.0.0' or index.get('corpus_sha256') != corpus_hash(chunks):
        raise ValueError('Wrong or stale Qwen index')
    rows = index['records']
    if len(rows) != len(chunks) or {r['content_id'] for r in rows} != {c.content_id for c in chunks}:
        raise ValueError('Corpus vector coverage mismatch')
    by_id = {r['content_id']: r for r in rows}
    for c in chunks:
        if by_id[c.content_id]['text_sha256'] != digest(embedding_text(c)):
            raise ValueError('Corpus text changed')
    vectors = {cid: normalized(row['vector']) for cid, row in by_id.items()}
    data = documents['query-vectors.json']
    rows = data['records']
    if data.get('encoder') != ENCODER or len(rows) != len(dataset['queries']) or {r['query_id'] for r in rows} != {q['query_id'] for q in dataset['queries']}:
        raise ValueError('Query vector coverage mismatch')
    queries = {r['query_id']: r for r in rows}
    for q in dataset['queries']:
        if queries[q['query_id']]['query_sha256'] != query_key(q['request']['query']):
            raise ValueError('Query text or instruction changed')
    return vectors, {qid: normalized(row['vector']) for qid, row in queries.items()}


def evaluate(documents):
    """Same candidates, BM25, tie breaks, relevance and metrics as the BGE evaluator."""
    chunks, dataset = load_inputs(Path('.'), documents)
    vectors, query_vectors = validate_vectors(documents, chunks, dataset)
    methods, records = {}, []
    for method in ['metadata', 'lexical', 'semantic']:
        positive, negative, empty_correct = [], 0, 0
        for q in dataset['queries']:
            req = RetrievalRequest.model_validate({**q['request'], 'method': method})
            started = perf_counter()
            if method == 'semantic':
                pool = candidates(chunks, req, authoring=True)
                scored = [(c.content_id, sum(a * b for a, b in zip(query_vectors[q['query_id']], vectors[c.content_id]))) for c in pool]
                ids = [cid for cid, score in sorted(scored, key=lambda item: (-item[1], item[0]))[:req.top_k]]
            else:
                ids = [h.chunk.content_id for h in retrieve(chunks, req, authoring=True, allow_fallback=False).hits]
            grades = q['relevance']
            if grades:
                recall = len(set(ids) & set(grades)) / len(grades)
                hit = int(any(cid in grades for cid in ids))
                dcg = sum((2 ** grades.get(cid, 0) - 1) / math.log2(i + 2) for i, cid in enumerate(ids))
                ideal = sum((2 ** v - 1) / math.log2(i + 2) for i, v in enumerate(sorted(grades.values(), reverse=True)[:req.top_k]))
                ndcg = dcg / ideal if ideal else 0.
                positive.append((q['concept_group'], recall, hit, ndcg))
            else:
                negative += 1
                empty_correct += int(not ids)
                recall = hit = ndcg = None
            records.append(dict(method=method, query_id=q['query_id'], source_group=q['source_group'],
                                retrieved_ids=ids, recall=recall, hit=hit, ndcg=ndcg,
                                ranking_ms=round((perf_counter() - started) * 1000, 3)))
        names = [(1, 'recall_at_3'), (2, 'hit_at_3'), (3, 'ndcg_at_3')]
        means = {name: sum(row[i] for row in positive) / len(positive) for i, name in names}
        by_concept = {c: {name: sum(row[i] for row in positive if row[0] == c) / sum(row[0] == c for row in positive)
                         for i, name in names} for c in sorted({row[0] for row in positive})}
        methods[method] = dict(**means, positive_queries=len(positive), no_eligible_content_cases=negative,
                               empty_results_correct=empty_correct, by_concept=by_concept)
    return dict(split=dataset['split'], label_status=dataset['label_status'], queries=len(dataset['queries']),
                corpus_chunks=len(chunks), corpus_sha256=corpus_hash(chunks), query_set_sha256=digest(dataset),
                k=3, methods=methods, semantic_run=True, encoder=ENCODER, records=records,
                limitations=['AI-authored dev labels, not reviewed independent test.',
                             'Small correlated query families; no significance or learning benefit claim.',
                             'Ranking times exclude model loading and query encoding.',
                             'Empty-scope cases do not test general out-of-domain abstention.'])


def equivalent(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if type(a) in (float, int) and type(b) in (float, int):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-10)
    return type(a) is type(b) and a == b


def comparison(documents, report):
    baseline = documents['bge-baseline.json']
    bge = baseline['evaluation']
    if baseline['query_set_sha256'] != digest(documents['queries.json']) or bge['corpus_sha256'] != report['corpus_sha256'] or bge['k'] != report['k']:
        raise ValueError('BGE baseline uses different corpus/query set/K')
    for method in ['metadata', 'lexical']:
        if not equivalent(bge['methods'][method], report['methods'][method]):
            raise ValueError('Baseline changed; comparison is not like-for-like')
    return {'metadata': report['methods']['metadata'], 'BM25': report['methods']['lexical'],
            'BGE-M3': bge['methods']['semantic'], 'Qwen3-Embedding-4B': report['methods']['semantic']}


def export_artifact(work_dir, output, environment, timings, input_manifest_sha256):
    work_dir, output = Path(work_dir), Path(output)
    raw = {name: (work_dir / name).read_bytes() for name in ARTIFACT_FILES}
    manifest = dict(schema_version='1.0.0', encoder=ENCODER, environment=environment, timings=timings,
                    corpus_sha256=json.loads(raw['index.json'])['corpus_sha256'],
                    input_manifest_sha256=input_manifest_sha256,
                    sha256={name: hashlib.sha256(value).hexdigest() for name, value in raw.items()})
    raw['run-manifest.json'] = json_bytes(manifest)
    with ZipFile(output, 'w', ZIP_DEFLATED) as bundle:
        for name, value in raw.items():
            bundle.writestr(name, value)
    return output


def import_artifact(archive, output=None):
    """Validate and recompute before saving into Qwen-only directories."""
    root = (ROOT / 'data/retrieval').resolve()
    output = Path(output or root / 'qwen3-4b-v1').resolve()
    if output.parent != root or not output.name.startswith('qwen3-4b-'):
        raise ValueError('Output must be a qwen3-4b-* directory directly inside data/retrieval')
    allowed = set(ARTIFACT_FILES + ['run-manifest.json'])
    with ZipFile(archive) as bundle:
        if set(bundle.namelist()) != allowed or len(bundle.namelist()) != len(allowed) or sum(i.file_size for i in bundle.infolist()) > 20 * 1024 * 1024:
            raise ValueError('Unexpected/oversized Qwen artifact')
        raw = {name: bundle.read(name) for name in allowed}
    docs = {name: json.loads(value) for name, value in raw.items()}
    manifest = docs['run-manifest.json']
    if manifest.get('encoder') != ENCODER or manifest.get('sha256') != {name: hashlib.sha256(value).hexdigest() for name, value in raw.items() if name != 'run-manifest.json'}:
        raise ValueError('Qwen artifact encoder/hash mismatch')
    from app.curriculum import load_curriculum
    registry, bank = load_curriculum()
    chunks = corpus(registry, bank)
    expected_queries = json.loads((ROOT / 'content/curriculum/retrieval.dev.v1.json').read_text(encoding='utf-8'))
    if docs['corpus.json'] != [c.model_dump(mode='json') for c in chunks] or docs['queries.json'] != expected_queries or manifest.get('corpus_sha256') != corpus_hash(chunks):
        raise ValueError('Artifact differs from current corpus/query set')
    calculated = evaluate(docs)
    reported = docs['evaluation.json']
    strip = lambda rows: [{k: v for k, v in row.items() if k != 'ranking_ms'} for row in rows]
    # Compare every report field except timings; no unverified metrics saved.
    checked_report = {**reported, 'records': strip(reported['records'])}
    checked_calculated = {**calculated, 'records': strip(calculated['records'])}
    if not equivalent(checked_report, checked_calculated):
        raise ValueError('Qwen evaluation does not match vectors')
    scores = comparison(docs, calculated)
    for name, value in raw.items():
        target = output / name
        if target.exists() and target.read_bytes() != value:
            raise ValueError('Existing Qwen result differs; use another qwen3-4b-* output directory')
    output.mkdir(parents=True, exist_ok=True)
    for name, value in raw.items():
        (output / name).write_bytes(value)
    return {'output': str(output), 'chunks': len(chunks), 'comparison': scores,
            'note': 'Research artifact only; BGE backend, flags and index remain unchanged.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare')
    import_cmd = commands.add_parser('import')
    import_cmd.add_argument('archive', type=Path)
    import_cmd.add_argument('--output', type=Path)
    eval_cmd = commands.add_parser('evaluate')
    eval_cmd.add_argument('--inputs', type=Path, default=ROOT / 'data/retrieval/qwen3-4b-v1')
    eval_cmd.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare()
    elif args.command == 'import':
        result = import_artifact(args.archive, args.output)
    else:
        docs = {name: json.loads((args.inputs / name).read_text(encoding='utf-8')) for name in ARTIFACT_FILES}
        report = evaluate(docs)
        if args.output:
            if args.output.exists():
                raise ValueError('Evaluation output exists; choose a new file')
            args.output.write_bytes(json_bytes(report))
        result = comparison(docs, report)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
