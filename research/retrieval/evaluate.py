"""Shared local/Colab retrieval evaluation, with grouped draft relevance labels."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.retrieval import candidates, corpus_hash, load_index, validate_index, retrieve, normalized, digest
from app.local_embedding import ENCODER
from app.retrieval_contracts import KnowledgeChunk, RetrievalRequest


def load_inputs(root, documents=None):
    read = lambda name: documents[name] if documents is not None else json.loads((root/name).read_text(encoding='utf-8'))
    chunks = [KnowledgeChunk.model_validate(c) for c in read('corpus.json')]
    queries = read('queries.json')
    if len({c.content_id for c in chunks}) != len(chunks) or not chunks:
        raise ValueError('Invalid corpus IDs')
    if queries['schema_version'] != '1.0.0' or not queries['queries'] or queries['split'] != 'authoring_dev' or queries['label_status'] != 'draft_ai_authored' or len({q['query_id'] for q in queries['queries']}) != len(queries['queries']):
        raise ValueError('Only unique draft development relevance queries allowed')
    for query in queries['queries']:
        request = RetrievalRequest.model_validate(query['request'])
        if request.top_k != 3:
            raise ValueError('This evaluator requires k=3')
        allowed = {c.content_id for c in candidates(chunks, request, authoring=True)}
        if any(k not in allowed or v not in (1,2,3) for k,v in query['relevance'].items()):
            raise ValueError('Relevance label outside eligible corpus/disclosure')
    if not any(q['relevance'] for q in queries['queries']):
        raise ValueError('At least one positive query is required')
    return chunks, queries


def query_key(query):
    return digest({'encoder':ENCODER,'query':query})


def save_query_vectors(queries, values):
    if len(values) != len(queries):
        raise ValueError('Query vector count mismatch')
    return {'encoder':ENCODER, 'records':[
        {'query_id':q['query_id'],'query_sha256':query_key(q['request']['query']),'vector':normalized(v)}
        for q,v in zip(queries,values)]}


def evaluate(root, *, semantic=False, documents=None):
    chunks, dataset = load_inputs(root, documents)
    query_vectors = {}
    if semantic:
        if documents is not None:
            validate_index(documents['index.json'], chunks)
        else:
            load_index(root/'index.json', chunks)
        data = documents['query-vectors.json'] if documents is not None else json.loads((root/'query-vectors.json').read_text(encoding='utf-8'))
        if data['encoder'] != ENCODER or len(data['records']) != len(dataset['queries']) or {r['query_id'] for r in data['records']} != {q['query_id'] for q in dataset['queries']}:
            raise ValueError('Query encoder/coverage mismatch')
        query_vectors = {r['query_id']:r for r in data['records']}
        for item in query_vectors.values():
            normalized(item['vector'])
    methods = ['metadata','lexical']+(['semantic'] if semantic else [])
    records, metrics = [], {}
    for method in methods:
        positives, empty_correct, negatives = [], 0, 0
        for q in dataset['queries']:
            request = RetrievalRequest.model_validate({**q['request'],'method':method})
            vector = None
            if semantic and method == 'semantic':
                item = query_vectors[q['query_id']]
                if item['query_sha256'] != query_key(request.query):
                    raise ValueError('Stale query vector')
                vector = item['vector']
            started = perf_counter()
            outcome = retrieve(chunks,request,authoring=True,index_path=root/'index.json',
                               query_vector=vector,allow_fallback=False,
                               index_document=documents['index.json'] if semantic and documents is not None else None)
            assert outcome.actual_method in (method,'none')
            retrieved = [h.chunk.content_id for h in outcome.hits]
            grades = q['relevance']
            if grades:
                recall = len(set(retrieved)&set(grades))/len(grades)
                hit = int(any(c in grades for c in retrieved))
                dcg = sum((2**grades.get(c,0)-1)/math.log2(i+2) for i,c in enumerate(retrieved))
                ideal = sum((2**v-1)/math.log2(i+2) for i,v in enumerate(sorted(grades.values(),reverse=True)[:request.top_k]))
                ndcg = dcg/ideal if ideal else 0.
                positives.append((q['concept_group'],recall,hit,ndcg))
            else:
                negatives+=1
                empty_correct+=int(not retrieved)
                recall=hit=ndcg=None
            records.append({'method':method,'query_id':q['query_id'],'source_group':q['source_group'],
                            'retrieved_ids':retrieved,'recall':recall,'hit':hit,'ndcg':ndcg,
                            'ranking_ms':round((perf_counter()-started)*1000,3)})
        means = {name:sum(row[i] for row in positives)/len(positives) for i,name in [(1,'recall_at_3'),(2,'hit_at_3'),(3,'ndcg_at_3')]}
        by_concept = {c:{name:sum(row[i] for row in positives if row[0]==c)/sum(row[0]==c for row in positives)
                         for i,name in [(1,'recall_at_3'),(2,'hit_at_3'),(3,'ndcg_at_3')]}
                      for c in sorted({row[0] for row in positives})}
        metrics[method] = {**means,'positive_queries':len(positives),'no_eligible_content_cases':negatives,
                           'empty_results_correct':empty_correct,'by_concept':by_concept}
    return {'split':dataset['split'],'label_status':dataset['label_status'], 'queries':len(dataset['queries']),
            'corpus_chunks':len(chunks),'corpus_sha256':corpus_hash(chunks),'k':3,'methods':metrics,
            'semantic_run':semantic,'encoder':ENCODER if semantic else None,
            'limitations':['Development queries and labels are AI-authored drafts, not independent reviewed test.',
                           'Small correlated query groups; no claim of statistical significance or learner benefit.',
                           'Ranking times exclude model loading and query encoding; benchmark them separately.',
                           'Cases without labels here only test empty metadata scope, not general out-of-domain abstention.'],
            'input_sha256':({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'corpus.json',root/'queries.json']} if documents is None else {}),
            'records':records}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs',type=Path,default=ROOT/'data/retrieval/pilot-input')
    parser.add_argument('--semantic',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=evaluate(args.inputs,semantic=args.semantic)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
