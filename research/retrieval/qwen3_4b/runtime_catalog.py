"""Separate Kaggle batch for trusted runtime queries; original experiment stays intact."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
from time import perf_counter
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT))
from app.qwen_query import ENCODER, digest, normalized
from research.retrieval.qwen3_4b import experiment

PREFIX = 'pilot-query-vectors-qwen3-4b/'
INPUT_NAME = 'pilot-query-vectors-qwen3-4b-input.zip'
OUTPUT_NAME = 'pilot-query-vectors-qwen3-4b.zip'
CODE_FILES = experiment.CODE_FILES + ['backend/app/qwen_query.py',
    'research/retrieval/qwen3_4b/runtime_catalog.py']
INPUT_FILES = CODE_FILES + ['specification.json', 'manifest.json']


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def archive(raw):
    stream = io.BytesIO()
    with ZipFile(stream, 'w', ZIP_DEFLATED) as bundle:
        for name, value in sorted(raw.items()):
            info = ZipInfo(PREFIX + name, date_time=(2026, 10, 19, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            bundle.writestr(info, value)
    return stream.getvalue()


def prepare(output=None):
    from app.curriculum import load_curriculum
    from app.qwen_catalog import specification
    spec = specification(*load_curriculum())
    # Match Linux checkout bytes even when a Windows editor used CRLF.
    raw = {name: (ROOT / name).read_bytes().replace(b'\r\n', b'\n') for name in CODE_FILES}
    raw['specification.json'] = json_bytes(spec)
    manifest = {'schema_version': '1.0.0', 'purpose': 'trusted-runtime-query-catalog',
        'encoder': ENCODER, 'specification_sha256': digest(spec),
        'sha256': {n: hashlib.sha256(v).hexdigest() for n, v in raw.items()}}
    raw['manifest.json'] = json_bytes(manifest)
    target = Path(output or ROOT / 'data/exports' / INPUT_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive(raw))
    return {'archive': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'queries': len(spec['queries']), 'specification_sha256': digest(spec)}


def read_input(source):
    source = Path(source)
    limit = 5 * 1024**2
    if source.is_file():
        if source.stat().st_size > limit:
            raise ValueError('Input too large')
        with ZipFile(source) as bundle:
            expected = {PREFIX + n for n in INPUT_FILES}
            if set(bundle.namelist()) != expected or len(bundle.namelist()) != len(expected):
                raise ValueError('Input allowlist mismatch')
            if sum(i.file_size for i in bundle.infolist()) > limit:
                raise ValueError('Input too large')
            raw = {n: bundle.read(PREFIX + n) for n in INPUT_FILES}
    else:
        if not (source / 'manifest.json').is_file():
            source = source / PREFIX
        if {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} != set(INPUT_FILES):
            raise ValueError('Input directory allowlist mismatch')
        if sum((source / n).stat().st_size for n in INPUT_FILES) > limit:
            raise ValueError('Input too large')
        raw = {n: (source / n).read_bytes() for n in INPUT_FILES}
    manifest = json.loads(raw['manifest.json'])
    spec = json.loads(raw['specification.json'])
    if (manifest.get('schema_version') != '1.0.0' or manifest.get('encoder') != ENCODER
            or manifest.get('purpose') != 'trusted-runtime-query-catalog'
            or spec.get('encoder') != ENCODER
            or manifest.get('specification_sha256') != digest(spec)
            or manifest.get('sha256') != {n: hashlib.sha256(v).hexdigest() for n,v in raw.items() if n != 'manifest.json'}):
        raise ValueError('Input hashes/configuration mismatch')
    return raw, spec


def run(source, output, cache):
    raw, spec = read_input(source)
    experiment.reset_peak_memory()
    started = perf_counter()
    model = experiment.load_model(Path(cache))
    experiment.gpu_sync()
    timings = {'model_load_seconds': round(perf_counter() - started, 3)}
    started = perf_counter()
    vectors = experiment.encode_texts(model, [q['text'] for q in spec['queries']], queries=True, batch_size=2)
    experiment.gpu_sync()
    timings['query_encode_seconds'] = round(perf_counter() - started, 3)
    document = {'schema_version': '1.0.0', 'specification': spec,
        'specification_sha256': digest(spec), 'records': [
            {'query_sha256': q['query_sha256'], 'vector': normalized(v)}
            for q,v in zip(spec['queries'], vectors)],
        'runtime': model.runtime, 'timings': timings, 'peak_gpu_memory_mib': experiment.peak_memory(),
        'note': 'Batch vectors for exact trusted queries; no new relevance evaluation or live model service.'}
    data = json_bytes(document)
    manifest = {'schema_version': '1.0.0', 'encoder': ENCODER,
        'input_manifest_sha256': hashlib.sha256(raw['manifest.json']).hexdigest(),
        'sha256': {'catalog.json': hashlib.sha256(data).hexdigest()}}
    target = Path(output)
    if target.exists():
        raise ValueError('Output exists; choose a fresh run path')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive({'catalog.json': data, 'run-manifest.json': json_bytes(manifest)}))
    return {'output': str(target), 'queries': len(vectors), 'dimensions': 2560, 'timings': timings,
            'peak_gpu_memory_mib': document['peak_gpu_memory_mib']}


def import_output(source, output=None):
    from app.curriculum import load_curriculum
    from app.qwen_catalog import DEFAULT_PATH, specification, validate
    source = Path(source)
    if source.stat().st_size > 10 * 1024**2:
        raise ValueError('Output ZIP too large')
    with ZipFile(source) as bundle:
        names = [PREFIX + 'catalog.json', PREFIX + 'run-manifest.json']
        if sorted(bundle.namelist()) != sorted(names) or sum(i.file_size for i in bundle.infolist()) > 10 * 1024**2:
            raise ValueError('Output allowlist/size mismatch')
        data = bundle.read(PREFIX + 'catalog.json')
        manifest = json.loads(bundle.read(PREFIX + 'run-manifest.json'))
    if (manifest.get('schema_version') != '1.0.0' or manifest.get('encoder') != ENCODER
            or manifest.get('sha256') != {'catalog.json': hashlib.sha256(data).hexdigest()}):
        raise ValueError('Output checksum/configuration mismatch')
    document = json.loads(data)
    spec = specification(*load_curriculum())
    validate(document, spec)
    # Bind the run to the uploaded code/spec manifest, without executing downloaded code.
    input_path = ROOT / 'data/exports' / INPUT_NAME
    input_raw, input_spec = read_input(input_path)
    if input_spec != spec or manifest.get('input_manifest_sha256') != hashlib.sha256(input_raw['manifest.json']).hexdigest():
        raise ValueError('Output does not match the prepared input')
    target = Path(output or DEFAULT_PATH)
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError('Catalog exists; choose another versioned destination')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {'catalog': str(target), 'queries': len(document['records']), 'specification_sha256': digest(spec)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'import'])
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'import' and args.input is None:
        parser.error('--input is required for import')
    print(json.dumps(prepare(args.output) if args.action == 'prepare' else import_output(args.input, args.output),
                     ensure_ascii=False, indent=2))
