"""Validate Colab JSON artifacts before saving; no pickle, model code or DB writes."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT))
from app.curriculum import load_curriculum
from app.retrieval import corpus, load_index, corpus_hash
from app.local_embedding import ENCODER
from research.retrieval.evaluate import evaluate

ALLOWED={'index.json','query-vectors.json','evaluation.json','run-manifest.json','corpus.json','queries.json'}


def equivalent(left, right):
    """Keep IDs/rankings exact; tolerate small cross-platform libm differences in metrics."""
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys()==right.keys() and all(equivalent(left[k],right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left)==len(right) and all(equivalent(a,b) for a,b in zip(left,right))
    if type(left) in (int,float) and type(right) in (int,float):
        return math.isclose(left,right,rel_tol=1e-9,abs_tol=1e-10)
    return type(left) is type(right) and left==right


def import_artifact(archive, output):
    root=(ROOT/'data/retrieval').resolve()
    output=output.resolve()
    if not output.is_relative_to(root) or output==root:
        raise ValueError('Output must be a child directory inside data/retrieval')
    with ZipFile(archive) as bundle:
        if set(bundle.namelist())!=ALLOWED or len(bundle.namelist())!=len(ALLOWED) or sum(i.file_size for i in bundle.infolist())>12*1024*1024:
            raise ValueError('Unexpected or oversized artifact archive')
        raw={name:bundle.read(name) for name in ALLOWED}
        documents={name:json.loads(value) for name,value in raw.items()}
    expected_hashes={name:hashlib.sha256(value).hexdigest() for name,value in raw.items() if name!='run-manifest.json'}
    if documents['run-manifest.json'].get('sha256') != expected_hashes:
        raise ValueError('Artifact file hash mismatch')
    if documents['run-manifest.json']['encoder']!=ENCODER:
        raise ValueError('Wrong embedding model/revision')
    registry,bank=load_curriculum()
    chunks=corpus(registry,bank)
    candidate=documents['index.json']
    from app.retrieval import build_index
    by_id={r['content_id']:r for r in candidate['records']}
    checked=build_index(chunks,[by_id[c.content_id]['vector'] for c in chunks])
    if candidate['encoder']!=ENCODER or candidate['corpus_sha256']!=checked['corpus_sha256'] or candidate['schema_version']!='1.0.0':
        raise ValueError('Stale corpus/model artifact')
    if len(by_id)!=len(chunks) or len(candidate['records'])!=len(chunks) or any(
        by_id[r['content_id']]['text_sha256']!=r['text_sha256'] for r in checked['records']):
        raise ValueError('Stale/duplicate corpus vector IDs or text hashes')
    if documents['corpus.json']!=[c.model_dump(mode='json') for c in chunks]:
        raise ValueError('Artifact teaching corpus differs from current content')
    if documents['queries.json']!=json.loads((ROOT/'content/curriculum/retrieval.dev.v1.json').read_text(encoding='utf-8')):
        raise ValueError('Artifact query set differs from current development dataset')
    if not documents['evaluation.json']['semantic_run'] or documents['evaluation.json']['corpus_sha256']!=corpus_hash(chunks):
        raise ValueError('Artifact lacks semantic evaluation')
    if documents['run-manifest.json']['corpus_sha256']!=corpus_hash(chunks):
        raise ValueError('Artifact manifest mismatch')
    recalculated=evaluate(output, semantic=True, documents=documents)
    reported=documents['evaluation.json']
    # Recompute all rankings/metrics from supplied vectors before writing. Timings are machine-dependent.
    without_timing=lambda records:[{k:v for k,v in r.items() if k!='ranking_ms'} for r in records]
    if not equivalent(reported['methods'],recalculated['methods']) or not equivalent(without_timing(reported['records']),without_timing(recalculated['records'])):
        raise ValueError('Evaluation does not match supplied vectors')
    encoded={name:json.dumps(value,ensure_ascii=False,indent=2)+'\n' for name,value in documents.items()}
    for name,content in encoded.items():
        target=output/name
        if target.exists() and target.read_text(encoding='utf-8')!=content:
            raise ValueError('Existing artifact differs; choose another --output directory instead of overwriting')
    output.mkdir(parents=True,exist_ok=True)
    for name,content in encoded.items():
        (output/name).write_text(content,encoding='utf-8')
    load_index(output/'index.json',chunks)
    return {'output':str(output),'chunks':len(chunks),'encoder':ENCODER,
            'note':'Corpus vectors imported. Runtime still needs the same BGE-M3 model to encode new queries.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'data/retrieval/bge-m3-v1')
    args=parser.parse_args()
    print(json.dumps(import_artifact(args.archive,args.output),ensure_ascii=False,indent=2))
