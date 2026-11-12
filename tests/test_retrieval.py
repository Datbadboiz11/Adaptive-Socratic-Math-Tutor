"""Graph boundaries, disclosure filtering, vector parity, Colab artifacts and grounding."""
import copy
import hashlib
import io
import json
import math
import os
import subprocess
from pathlib import Path
import sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
sys.path.insert(0, str(ROOT))
from app import curriculum_graph as graph, local_embedding, pilot_grounding
from app.curriculum import load_curriculum
from app.local_embedding import ENCODER, EmbeddingUnavailable
from app.pilot_analyzer import analyze
from app.retrieval import (corpus, corpus_hash, candidates, embedding_text, build_index,
                           validate_index, load_index, retrieve, normalized)
from app.retrieval_contracts import RetrievalRequest, GroundingSubmission
from research.retrieval.evaluate import evaluate, save_query_vectors, query_key
from scripts.exports.prepare_retrieval_colab import CODE_FILES, prepare
from scripts.exports import import_retrieval_artifact as importer

REGISTRY, BANK = load_curriculum()
CHUNKS = corpus(REGISTRY, BANK)
DATASET = json.loads((ROOT/'content/curriculum/retrieval.dev.v1.json').read_text(encoding='utf-8'))


def vector(i):
    result = [0.]*1024
    result[i % 1024] = 1.
    return result


def request(**kwargs):
    return RetrievalRequest(query='Phân phối phép nhân vào ngoặc', concept_ids=['A02'], **kwargs)


def documents():
    docs = {'corpus.json':[c.model_dump(mode='json') for c in CHUNKS], 'queries.json':copy.deepcopy(DATASET),
            'index.json':build_index(CHUNKS, [vector(i) for i in range(len(CHUNKS))])}
    docs['query-vectors.json'] = save_query_vectors(DATASET['queries'], [vector(i % 40) for i in range(90)])
    docs['evaluation.json'] = evaluate(Path('.'), semantic=True, documents=docs)
    return docs


def archive(path, docs):
    raw = {k:(json.dumps(v, ensure_ascii=False, indent=2)+'\n').encode() for k,v in docs.items() if k != 'run-manifest.json'}
    manifest = {'schema_version':'1.0.0', 'encoder':ENCODER, 'corpus_sha256':corpus_hash(CHUNKS),
                'sha256':{k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}}
    raw['run-manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    with ZipFile(path, 'w', ZIP_DEFLATED) as bundle:
        for name,value in raw.items():
            bundle.writestr(name, value)


def test_corpus_positive_projection_and_drafts():
    assert len(CHUNKS) == 40
    assert {c.kind for c in CHUNKS} == {'explanation','hint'}
    assert not any(c.approved for c in CHUNKS)
    assert all('MVP' not in c.text for c in CHUNKS)
    encoded = json.dumps([c.model_dump() for c in CHUNKS])
    assert all(private not in encoded for private in ['reference_answer','reference_steps','response_steps','incorrect_response'])
    assert all(hashlib.sha256(c.text.encode()).hexdigest() == c.text_sha256 for c in CHUNKS)


@pytest.mark.parametrize('level', [1,2,3])
def test_disclosure_filter_before_ranking(level):
    for method in ['metadata','lexical','semantic']:
        req = request(hint_level=level, method=method)
        result = retrieve(CHUNKS, req, authoring=True, index_document=build_index(CHUNKS,[vector(i) for i in range(40)]), query_vector=vector(0))
        assert result.candidate_count == level
        assert all(h.chunk.concept_id == 'A02' and h.chunk.kind == 'hint' and h.chunk.hint_level <= level for h in result.hits)


def test_unapproved_content_never_calls_query_encoder():
    def forbidden(_):
        raise AssertionError('Encoder should not be called for empty eligible scope')
    result = retrieve(CHUNKS, request(), query_encoder=forbidden)
    assert result.actual_method == 'none' and result.reason == 'no_eligible_content'
    # A simulated approval only opens that exact content; changing metadata invalidates old index.
    approved = CHUNKS[0].model_copy(update={'approved':True, 'review_status':'human_approved'})
    updated = [approved, *CHUNKS[1:]]
    req = RetrievalRequest(query='x', concept_ids=[approved.concept_id], purpose=approved.kind, method='metadata')
    assert [h.chunk.content_id for h in retrieve(updated, req).hits] == [approved.content_id]
    with pytest.raises(EmbeddingUnavailable, match='stale'):
        validate_index(build_index(CHUNKS,[vector(i) for i in range(40)]),updated)


def test_explanation_does_not_mix_with_hints_and_no_lexical_overlap():
    result = retrieve(CHUNKS,request(purpose='explanation',method='metadata'),authoring=True)
    assert len(result.hits)==1 and result.hits[0].chunk.hint_level==0
    req=request(method='lexical').model_copy(update={'query':'zzzzzzzzzzzz'})
    assert retrieve(CHUNKS,req,authoring=True).reason=='no_lexical_overlap'


def test_cosine_order_and_stable_ties():
    docs=build_index(CHUNKS,[vector(i) for i in range(40)])
    wanted=next(i for i,c in enumerate(CHUNKS) if c.content_id=='A02-hint-3')
    result=retrieve(CHUNKS,request(hint_level=3),authoring=True,index_document=docs,query_vector=vector(wanted))
    assert result.actual_method=='semantic' and result.embedding_revision==ENCODER['revision']
    assert result.hits[0].chunk.content_id=='A02-hint-3' and result.hits[0].score==1
    assert [h.chunk.content_id for h in result.hits[1:]]==['A02-hint-1','A02-hint-2']
    assert [h.chunk.content_id for h in retrieve(CHUNKS,request(hint_level=3,method='metadata'),authoring=True).hits]==['A02-hint-1','A02-hint-2','A02-hint-3']


@pytest.mark.parametrize('change', ['revision','corpus','text','duplicate','missing','wrong_dimension','nan','zero'])
def test_invalid_index_is_rejected(change):
    data=copy.deepcopy(build_index(CHUNKS,[vector(i) for i in range(40)]))
    if change=='revision': data['encoder']['revision']='other'
    elif change=='corpus': data['corpus_sha256']='other'
    elif change=='text': data['records'][0]['text_sha256']='other'
    elif change=='duplicate': data['records'][1]['content_id']=data['records'][0]['content_id']
    elif change=='missing': data['records'].pop()
    elif change=='wrong_dimension': data['records'][0]['vector']=[1.]
    elif change=='nan': data['records'][0]['vector'][0]=float('nan')
    elif change=='zero': data['records'][0]['vector']=[0.]*1024
    with pytest.raises(EmbeddingUnavailable): validate_index(data,CHUNKS)


@pytest.mark.parametrize('bad',[[],[True]*1024,[1e308]*1024,[float('inf')]*1024])
def test_vector_rejects_nonfinite_bool_dimensions_and_overflow(bad):
    with pytest.raises(EmbeddingUnavailable): normalized(bad)


def test_fallback_is_explicit_and_forbidden_during_benchmark(tmp_path):
    result=retrieve(CHUNKS,request(),authoring=True,index_path=tmp_path/'missing.json')
    assert result.requested_method=='semantic' and result.actual_method=='lexical'
    assert result.fallback_reason=='index_unavailable' and result.embedding_model is None
    with pytest.raises(EmbeddingUnavailable):
        retrieve(CHUNKS,request(),authoring=True,index_path=tmp_path/'missing.json',allow_fallback=False)


def test_runtime_never_downloads_and_optional_flag(monkeypatch):
    monkeypatch.delenv('LOCAL_EMBEDDING_ENABLED',raising=False)
    with pytest.raises(EmbeddingUnavailable,match='disabled'): local_embedding.encode_query('text')
    seen={}
    def constructor(*args,**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(eval=lambda:None)
    monkeypatch.setitem(sys.modules,'sentence_transformers',SimpleNamespace(SentenceTransformer=constructor))
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace())
    model=local_embedding.load_model(download=False)
    assert seen['local_files_only'] is True and seen['trust_remote_code'] is False
    assert seen['revision']==ENCODER['revision'] and model.max_seq_length==512


def test_tokenizer_length_rejects_truncation_and_sanitizes_failure():
    model=SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda *a,**k:[1]*513))
    with pytest.raises(EmbeddingUnavailable,match='too_long'): local_embedding.encode_texts(model,['x'])
    def broken(*a,**k): raise RuntimeError('sensitive local path')
    model.tokenizer.encode=broken
    with pytest.raises(EmbeddingUnavailable,match='local_inference_failed'): local_embedding.encode_texts(model,['x'])


def test_concurrent_runtime_first_requests_load_model_once(monkeypatch):
    import time
    calls=[]; model=object()
    def load(**kwargs):
        calls.append(kwargs)
        time.sleep(.02)
        return model
    monkeypatch.setattr(local_embedding,'load_model',load)
    monkeypatch.setenv('EMBEDDING_DEVICE','cpu')
    local_embedding._cached_runtime_model.cache_clear()
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(lambda _:local_embedding.runtime_model(),range(4)))==[model]*4
        assert len(calls)==1 and 'download' not in calls[0]
    finally:
        local_embedding._cached_runtime_model.cache_clear()


@pytest.mark.parametrize('concept',[p.concept_id for p in BANK.packs])
def test_prerequisite_paths_are_directed_bounded_and_reviewed(concept):
    paths=graph.paths(REGISTRY,concept,authoring=True)
    edges={e.edge_id:e for e in REGISTRY.edges}
    assert graph.paths(REGISTRY,concept)==[]
    for path in paths:
        assert path.depth==len(path.edge_ids)==len(path.concept_ids)-1<=2
        assert path.concept_ids[-1]==concept
        for i,eid in enumerate(path.edge_ids):
            edge=edges[eid]
            assert edge.relation=='PREREQUISITE_OF'
            assert (edge.source_concept_id,edge.target_concept_id)==tuple(path.concept_ids[i:i+2])


def test_graph_unknown_depth_and_public_path_approval():
    for depth in (0,3):
        with pytest.raises(ValueError): graph.paths(REGISTRY,'A02',max_depth=depth)
    with pytest.raises(ValueError): graph.paths(REGISTRY,'unknown')
    reg=REGISTRY.model_copy(deep=True)
    path=graph.paths(reg,'E02',authoring=True)[-1]
    for c in reg.concepts:
        if c.concept_id in path.concept_ids:
            c.review.status='human_approved'; c.alignment.status='human_approved'
    for e in reg.edges:
        if e.edge_id in path.edge_ids: e.review.status='human_approved'
    assert path.edge_ids in [p.edge_ids for p in graph.paths(reg,'E02')]
    next(e for e in reg.edges if e.edge_id==path.edge_ids[-1]).review.status='draft'
    assert path.edge_ids not in [p.edge_ids for p in graph.paths(reg,'E02')]


def test_neo4j_parameterized_snapshot_import_and_parity(monkeypatch):
    driver=graph.Neo4jGraph(password='test-only')
    calls=[]
    def fake(statement,parameters=None):
        calls.append((statement,parameters))
        return [] if statement.startswith('CREATE') else [{'snapshot_id':graph.snapshot_id(REGISTRY)}]
    monkeypatch.setattr(driver,'query',fake)
    assert driver.import_registry(REGISTRY)['edges']==68
    assert len(calls)==3 and all('DELETE' not in s.upper() for s,p in calls)
    assert len(calls[-1][1]['nodes'])==40 and len(calls[-1][1]['edges'])==68
    expected=graph.paths(REGISTRY,'E02',authoring=True)
    def read(statement,parameters):
        return ([{'registry_json':REGISTRY.model_dump_json()}] if 'registry_json AS' in statement else
                [{'concept_ids':p.concept_ids,'edge_ids':p.edge_ids} for p in expected])
    monkeypatch.setattr(driver,'query',read)
    assert driver.prerequisites(REGISTRY,'E02',authoring=True)==expected
    assert driver.prerequisites(REGISTRY,'E02')==[]
    monkeypatch.setattr(driver,'query',lambda *a:[{'registry_json':'stale'}])
    with pytest.raises(graph.GraphUnavailable,match='stale'): driver.prerequisites(REGISTRY,'E02')


@pytest.mark.parametrize('payload',[{'errors':[{'message':'password secret'}]}, {'data':{'fields':['x','x'],'values':[[1,2]]}}, {'data':{'fields':['x'],'values':[[1,2]]}}, {}])
def test_neo4j_http_202_errors_and_bad_responses_are_sanitized(monkeypatch,payload):
    class Response(io.BytesIO):
        pass
    monkeypatch.setattr(graph,'build_opener',lambda *a:SimpleNamespace(open=lambda *a,**k:Response(json.dumps(payload).encode())))
    with pytest.raises(graph.GraphUnavailable) as exc:
        graph.Neo4jGraph(password='test-only').query('RETURN $n',{'n':1})
    assert 'secret' not in str(exc.value) and 'test-only' not in str(exc.value)


def test_neo4j_request_and_explicit_local_fallback(monkeypatch):
    seen={}
    def open_request(req,**kwargs):
        seen.update(url=req.full_url,body=json.loads(req.data),headers=req.headers,timeout=kwargs['timeout'])
        return io.BytesIO(b'{"data":{"fields":["n"],"values":[[1]]}}')
    monkeypatch.setattr(graph,'build_opener',lambda *a:SimpleNamespace(open=open_request))
    assert graph.Neo4jGraph(password='test-only').query('RETURN $n',{'n':1})==[{'n':1}]
    assert seen['body']['parameters']=={'n':1} and seen['timeout']==5 and seen['url'].endswith('/query/v2')
    assert graph.NoRedirect().redirect_request(None,None,None,None,None,None) is None
    monkeypatch.setenv('NEO4J_PASSWORD','')
    routes,provider,reason=graph.prerequisites(REGISTRY,'E02',authoring=True,provider='neo4j')
    assert provider=='registry_fallback' and reason and routes


@pytest.mark.parametrize('url',['http://user:secret@localhost:7474','file:///abc','https://example.com/path','http://localhost?token=secret'])
def test_graph_configuration_refuses_credentials_or_invalid_endpoint(url):
    with pytest.raises(graph.GraphUnavailable): graph.Neo4jGraph(url=url,password='test-only')


@pytest.mark.parametrize('pack',BANK.packs,ids=lambda p:p.concept_id)
def test_grounding_each_pilot_logs_evidence_and_does_not_update_bkt(monkeypatch,pack):
    monkeypatch.setattr(pilot_grounding,'analyze_bounded',analyze)
    error=pack.errors[0]
    problem=next(p for p in pack.problems if p.case_id==error.problem_id)
    body=GroundingSubmission(submission_kind='steps',steps=error.response_steps,method='metadata')
    result=pilot_grounding.ground(REGISTRY,BANK,pack,problem,body,provider='registry')
    assert result.analysis.assessment.assessment_status=='verified_incorrect'
    assert result.graph_provider=='registry' and not result.updates_student_model
    assert result.log['source_content_ids']==[h.chunk.content_id for h in result.retrieval.hits]
    assert result.log['edge_paths']==[p.edge_ids for p in result.prerequisites]
    assert all(h.chunk.hint_level==1 for h in result.retrieval.hits)
    assert problem.reference_answer not in result.retrieval.query or len(problem.reference_answer)<3
    assert 'steps' not in result.log and 'reference_answer' not in result.log


@pytest.mark.parametrize('steps,reason',[(['giải thích bằng lời'],'await_clarification'),(['3x+6'],'no_support_required')])
def test_grounding_abstains_for_uncertain_or_completed_trace(monkeypatch,steps,reason):
    monkeypatch.setattr(pilot_grounding,'analyze_bounded',analyze)
    pack=next(p for p in BANK.packs if p.concept_id=='A02')
    problem=next(p for p in pack.problems if p.case_id=='P-A02-01')
    result=pilot_grounding.ground(REGISTRY,BANK,pack,problem,GroundingSubmission(submission_kind='steps',steps=steps),provider='registry')
    assert result.retrieval.reason==reason and not result.retrieval.hits


def test_evaluation_recomputes_metrics_and_requires_complete_query_vectors():
    docs=documents()
    report=docs['evaluation.json']
    assert report['queries']==90 and report['methods']['semantic']['positive_queries']==80
    for method,metrics in report['methods'].items():
        rows=[r for r in report['records'] if r['method']==method and r['recall'] is not None]
        assert metrics['recall_at_3']==sum(r['recall'] for r in rows)/80
        assert all(0<=r['ndcg']<=1.0000000001 for r in rows)
        assert metrics['empty_results_correct']==10
    docs['query-vectors.json']['records'][-1]=docs['query-vectors.json']['records'][0]
    with pytest.raises(ValueError,match='coverage'): evaluate(Path('.'),semantic=True,documents=docs)


def test_evaluator_refuses_stale_query_vector_and_invalid_labels():
    docs=documents()
    docs['query-vectors.json']['records'][0]['query_sha256']='stale'
    with pytest.raises(ValueError,match='Stale'): evaluate(Path('.'),semantic=True,documents=docs)
    docs['queries.json']['queries'][0]['relevance']={'A02-hint-3':3}
    with pytest.raises(ValueError,match='Relevance'): evaluate(Path('.'),documents=docs)


def test_colab_metrics_and_rankings_reproduce_across_python_hash_seeds(tmp_path):
    # Colab and Windows use different hash seeds: ranking sums must be deterministic.
    docs=documents()
    for name,value in docs.items():
        (tmp_path/name).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    # Run the packaged evaluator outside the repo with a fresh interpreter/modules.
    packaged=tmp_path/'isolated-bundle'
    with ZipFile(prepare()['archive']) as bundle:
        for name in CODE_FILES:
            target=packaged/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(bundle.read('pilot-retrieval/'+name))
    for seed in ('1','999'):
        output=tmp_path/f'evaluation-{seed}.json'
        process=subprocess.run([sys.executable,'-P','-X','utf8',str(packaged/'research/retrieval/evaluate.py'),
            '--inputs',str(tmp_path),'--semantic','--output',str(output)],
            cwd=tmp_path,env={**{k:v for k,v in os.environ.items() if k!='PYTHONPATH'},'PYTHONHASHSEED':seed},capture_output=True,text=True,encoding='utf-8',timeout=30)
        assert process.returncode==0,process.stderr
        report=json.loads(output.read_text(encoding='utf-8'))
        assert report['methods']==docs['evaluation.json']['methods']
        strip_time=lambda rows:[{k:v for k,v in r.items() if k!='ranking_ms'} for r in rows]
        assert strip_time(report['records'])==strip_time(docs['evaluation.json']['records'])


def test_prepare_zip_allowlist_and_hashes(tmp_path, monkeypatch):
    # Export tests must never rewrite the user's prepared data/exports bundle.
    from scripts.exports import prepare_retrieval_colab as exporter
    for name in CODE_FILES + ['content/curriculum/retrieval.dev.v1.json']:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    result=prepare()
    with ZipFile(result['archive']) as bundle:
        names=bundle.namelist()
        assert set(names)=={'pilot-retrieval/'+n for n in CODE_FILES+['corpus.json','queries.json','manifest.json']}
        manifest=json.loads(bundle.read('pilot-retrieval/manifest.json'))
        assert all(hashlib.sha256(bundle.read('pilot-retrieval/'+n)).hexdigest()==v for n,v in manifest['sha256'].items())
        assert not any('.env' in n or 'pilot.v1.json' in n or 'assistments' in n for n in names)


def test_import_colab_artifact_and_refuse_existing_different_output(tmp_path,monkeypatch):
    monkeypatch.setattr(importer,'ROOT',tmp_path)
    (tmp_path/'content/curriculum').mkdir(parents=True)
    (tmp_path/'content/curriculum/retrieval.dev.v1.json').write_text(json.dumps(DATASET),encoding='utf-8')
    docs=documents()
    # Windows and Colab libm may differ at the last floating-point bits.
    docs['evaluation.json']['methods']['semantic']['ndcg_at_3']+=1e-12
    path=tmp_path/'artifact.zip'; archive(path,docs)
    target=tmp_path/'data/retrieval/v1'
    assert importer.import_artifact(path,target)['chunks']==40
    assert len(load_index(target/'index.json',CHUNKS))==40
    assert importer.import_artifact(path,target)['chunks']==40
    (target/'index.json').write_text('user change',encoding='utf-8')
    with pytest.raises(ValueError,match='Existing'): importer.import_artifact(path,target)
    assert (target/'index.json').read_text()=='user change'
    with pytest.raises(ValueError,match='child directory'): importer.import_artifact(path,tmp_path/'outside')


@pytest.mark.parametrize('change',['report','model','query','text','duplicate'])
def test_import_rejects_tampered_artifacts_before_writing(tmp_path,monkeypatch,change):
    monkeypatch.setattr(importer,'ROOT',tmp_path)
    (tmp_path/'content/curriculum').mkdir(parents=True)
    (tmp_path/'content/curriculum/retrieval.dev.v1.json').write_text(json.dumps(DATASET),encoding='utf-8')
    docs=documents()
    if change=='report': docs['evaluation.json']['methods']['semantic']['hit_at_3']=100
    elif change=='model': docs['index.json']=copy.deepcopy(docs['index.json']); docs['index.json']['encoder']['revision']='other'
    elif change=='query': docs['query-vectors.json']['records'][0]['query_sha256']='other'
    elif change=='text': docs['index.json']['records'][0]['text_sha256']='other'
    elif change=='duplicate': docs['index.json']['records'][1]['content_id']=docs['index.json']['records'][0]['content_id']
    path=tmp_path/'artifact.zip'; archive(path,docs)
    target=tmp_path/'data/retrieval/v1'
    with pytest.raises((ValueError, KeyError)): importer.import_artifact(path,target)
    assert not target.exists()


@pytest.mark.parametrize('runtime', ['colab', 'kaggle_zip', 'kaggle_extracted'])
def test_notebook_compiles_and_mock_run_exports_validated_json(tmp_path,monkeypatch,runtime):
    """Structural dry run with synthetic vectors. This is NOT a BGE-M3 GPU benchmark."""
    notebook=json.loads((ROOT/'research/retrieval/bge_m3_colab.ipynb').read_text(encoding='utf-8'))
    assert notebook['nbformat']==4 and len({c['id'] for c in notebook['cells']})==len(notebook['cells'])
    cells=[''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code']
    for source in cells: compile(source,'notebook','exec')
    prepared=prepare(); source_zip=Path(prepared['archive']).read_bytes()
    downloaded=[]
    fake_files=SimpleNamespace(upload=lambda:{'pilot-retrieval-input.zip':source_zip},download=lambda p:downloaded.append(p))
    kaggle_input=tmp_path/'kaggle-input'
    kaggle_work=tmp_path/'kaggle-working'
    kaggle_cache=tmp_path/'kaggle-temp'
    if runtime.startswith('kaggle'):
        # Nested mount layout; input is immutable, output must be at the working root.
        attached=kaggle_input/'datasets/team/pilot/versions/1'
        attached.mkdir(parents=True)
        if runtime=='kaggle_zip':
            (attached/'pilot-retrieval-input.zip').write_bytes(source_zip)
        else:
            with ZipFile(io.BytesIO(source_zip)) as bundle:
                for name in bundle.namelist():
                    target=attached/name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(bundle.read(name))
        before={p.relative_to(attached).as_posix():p.read_bytes() for p in attached.rglob('*') if p.is_file()}
        # A Kaggle run must not import Colab or require upload/download UI.
        monkeypatch.setitem(sys.modules,'google.colab',None)
    else:
        monkeypatch.setitem(sys.modules,'google.colab',SimpleNamespace(files=fake_files))
    ns={}
    # Redirect /content scratch paths into pytest's isolated workspace directory.
    first=cells[0].replace("Path('/content')",f'Path({str(tmp_path)!r})')
    for original,target in [('/kaggle/input',kaggle_input),('/kaggle/working',kaggle_work),('/kaggle/temp',kaggle_cache)]:
        first=first.replace(f'Path({original!r})',f'Path({str(target)!r})')
    exec(first,ns)
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(__version__='dry-run',version=SimpleNamespace(cuda='dry-run'),
        cuda=SimpleNamespace(is_available=lambda:True,get_device_name=lambda _: 'FAKE GPU - structural test only',
            synchronize=lambda:None,reset_peak_memory_stats=lambda:None,max_memory_allocated=lambda:0)))
    model_calls=[]
    def fake_model(**kwargs):
        model_calls.append(kwargs)
        return object()
    monkeypatch.setattr(local_embedding,'load_model',fake_model)
    monkeypatch.setattr(local_embedding,'encode_texts',lambda model,texts,**k:[vector(i) for i,_ in enumerate(texts)])
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata,'version',lambda name:'dry-run')
    for source in cells[2:]: exec(source,ns)  # Skip only real pip installation.
    if runtime.startswith('kaggle'):
        assert ns['RUNTIME_PLATFORM']=='kaggle' and downloaded==[]
        output=kaggle_work/'pilot-retrieval-bge-m3.zip'
        assert ns['output_zip']==output and output.is_file()
        assert model_calls[0]['cache_folder']==kaggle_cache/'bge-m3-model-cache'
        after={p.relative_to(attached).as_posix():p.read_bytes() for p in attached.rglob('*') if p.is_file()}
        assert before==after
    else:
        assert ns['RUNTIME_PLATFORM']=='colab' and len(downloaded)==1
        output=Path(downloaded[0])
        assert output==tmp_path/'pilot-retrieval-bge-m3.zip'
    with ZipFile(output) as bundle:
        assert set(bundle.namelist())==importer.ALLOWED
        assert json.loads(bundle.read('run-manifest.json'))['environment']['runtime_platform']==ns['RUNTIME_PLATFORM']
    monkeypatch.setattr(importer,'ROOT',tmp_path)
    (tmp_path/'content/curriculum').mkdir(parents=True,exist_ok=True)
    (tmp_path/'content/curriculum/retrieval.dev.v1.json').write_text(json.dumps(DATASET),encoding='utf-8')
    assert importer.import_artifact(output,tmp_path/'data/retrieval/from-notebook')['chunks']==40


@pytest.mark.parametrize('case,match', [
    ('missing','Chưa có gói input'),
    ('multiple','Có nhiều gói input'),
    ('tampered','SHA256 sai'),
    ('unexpected','ngoài danh sách'),
])
def test_kaggle_notebook_rejects_invalid_input_before_writing(tmp_path,monkeypatch,case,match):
    notebook=json.loads((ROOT/'research/retrieval/bge_m3_colab.ipynb').read_text(encoding='utf-8'))
    first=''.join(next(c for c in notebook['cells'] if c['cell_type']=='code')['source'])
    input_root=tmp_path/'input'
    output_root=tmp_path/'working'
    input_root.mkdir()
    source_zip=Path(prepare()['archive']).read_bytes()
    if case=='multiple':
        for name in ['a','b']:
            attached=input_root/name
            attached.mkdir()
            (attached/'pilot-retrieval-input.zip').write_bytes(source_zip)
    elif case in ['tampered','unexpected']:
        with ZipFile(io.BytesIO(source_zip)) as bundle:
            for name in bundle.namelist():
                target=input_root/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(bundle.read(name))
        if case=='tampered':
            (input_root/'pilot-retrieval/backend/app/local_embedding.py').write_text('changed',encoding='utf-8')
        else:
            (input_root/'pilot-retrieval/extra.py').write_text('unexpected',encoding='utf-8')
    first=first.replace("Path('/kaggle/input')",f'Path({str(input_root)!r})')
    first=first.replace("Path('/kaggle/working')",f'Path({str(output_root)!r})')
    monkeypatch.setitem(sys.modules,'google.colab',None)
    with pytest.raises(ValueError,match=match):
        exec(first,{})
    assert not output_root.exists()


@pytest.mark.skipif(os.getenv('SKIP_ASGI_TESTS')=='1',reason='Windows loopback TestClient unavailable; run on CI')
def test_grounding_api_auth_flags_and_private_projection(monkeypatch):
    from app.main import app
    from app.sessions import principal
    from app.pilot_api import require_preview,require_grounding
    app.dependency_overrides[principal]=lambda:{'student_id':'test'}
    try:
        client=TestClient(app)
        monkeypatch.setenv('PILOT_ANALYZER_ENABLED','false')
        monkeypatch.setenv('PILOT_GROUNDING_ENABLED','true')
        assert client.post('/api/v1/pilot/retrieve',json=request(method='metadata').model_dump()).status_code==403
        monkeypatch.setenv('PILOT_ANALYZER_ENABLED','true')
        monkeypatch.setenv('PILOT_GROUNDING_ENABLED','false')
        assert client.post('/api/v1/pilot/retrieve',json=request(method='metadata').model_dump()).status_code==403
        monkeypatch.setenv('PILOT_GROUNDING_ENABLED','true')
        response=client.post('/api/v1/pilot/retrieve',json=request(method='metadata').model_dump())
        assert response.status_code==200 and response.json()['mode']=='internal_authoring_preview'
        assert 'reference_answer' not in response.text
        app.dependency_overrides.clear()
        assert client.post('/api/v1/pilot/retrieve',json=request(method='metadata').model_dump()).status_code==401
    finally:
        app.dependency_overrides.clear()
