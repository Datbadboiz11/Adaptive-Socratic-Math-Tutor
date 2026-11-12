"""Allowlisted teaching-only Colab inputs. Never package .env or student records."""
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.curriculum import load_curriculum
from app.curriculum_graph import snapshot_id
from app.retrieval import corpus,corpus_hash
from app.local_embedding import ENCODER

CODE_FILES=['backend/app/__init__.py','backend/app/contracts.py','backend/app/curriculum.py',
            'backend/app/pilot_contracts.py','backend/app/retrieval_contracts.py','backend/app/retrieval.py',
            'backend/app/local_embedding.py','research/retrieval/evaluate.py','research/retrieval/requirements.txt']


def prepare():
    registry,bank=load_curriculum()
    chunks=corpus(registry,bank)
    out=ROOT/'data/retrieval/pilot-input'
    out.mkdir(parents=True,exist_ok=True)
    content=json.dumps([c.model_dump(mode='json') for c in chunks],ensure_ascii=False,indent=2)+'\n'
    (out/'corpus.json').write_text(content,encoding='utf-8')
    query_source=ROOT/'content/curriculum/retrieval.dev.v1.json'
    (out/'queries.json').write_bytes(query_source.read_bytes())
    manifest={'schema_version':'1.0.0','purpose':'Internal draft pilot retrieval, no private solutions or student data',
              'content_version':bank.content_version,'graph_snapshot_id':snapshot_id(registry),
              'corpus_sha256':corpus_hash(chunks),'encoder':ENCODER,
              'sha256':{'corpus.json':hashlib.sha256((out/'corpus.json').read_bytes()).hexdigest(),
                        'queries.json':hashlib.sha256((out/'queries.json').read_bytes()).hexdigest(),
                        **{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in CODE_FILES}}}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=ROOT/'data/exports/pilot-retrieval-input.zip'
    archive.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(archive,'w',ZIP_DEFLATED) as bundle:
        for name in ['corpus.json','queries.json','manifest.json']:
            bundle.write(out/name,'pilot-retrieval/'+name)
        for name in CODE_FILES:
            bundle.write(ROOT/name,'pilot-retrieval/'+name)
    return {'archive':str(archive),'chunks':len(chunks),'queries':len(json.loads(query_source.read_text(encoding='utf-8'))['queries']),
            'corpus_sha256':manifest['corpus_sha256']}


if __name__=='__main__':
    print(json.dumps(prepare(),ensure_ascii=False,indent=2))
