"""Replay saved Qwen queries through real pgvector; not online inference evidence."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.curriculum import load_curriculum
from app.curriculum_graph import snapshot_id
from app.retrieval import corpus, candidates
from app.retrieval_contracts import RetrievalRequest
from app.rag_store import PgVectorStore
from app.qwen_query import ENCODER, query_key


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,default=ROOT/'data/retrieval/qwen3-4b-v1')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    read=lambda n:json.loads((args.inputs/n).read_text(encoding='utf-8'))
    registry,bank=load_curriculum(); chunks=corpus(registry,bank)
    dataset=read('queries.json'); saved=read('query-vectors.json'); report=read('evaluation.json')
    if saved['encoder']!=ENCODER: raise ValueError('Wrong query encoder')
    rows={r['query_id']:r for r in saved['records']}
    if len(rows)!=len(dataset['queries']): raise ValueError('Missing query vectors')
    expected={r['query_id']:r for r in report['records'] if r['method']=='semantic'}
    store=PgVectorStore(snapshot_id(registry)); cid=store.ready(chunks)
    comparisons=[]
    for q in dataset['queries']:
        req=RetrievalRequest.model_validate(q['request']); row=rows[q['query_id']]
        if row['query_sha256']!=query_key(req.query): raise ValueError('Stale query')
        _,ranked=store.search(chunks,req,row['vector'],candidates(chunks,req,authoring=True),authoring=True)
        ids=[c.content_id for c,s in ranked]
        comparisons.append({'query_id':q['query_id'],'matches_saved_ranking':ids==expected[q['query_id']]['retrieved_ids'],
                            'retrieved_ids':ids})
    result={'collection_id':cid,'queries':len(comparisons),'matching_rankings':sum(r['matches_saved_ranking'] for r in comparisons),
            'note':'Replay with saved query vectors; does not prove encoding of new queries. pgvector stores float32.', 'records':comparisons}
    if args.output:
        if args.output.exists(): raise ValueError('Output exists; preserving it')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2))
    if result['matching_rankings']!=len(comparisons): raise SystemExit('Ranking drift: inspect precision/ties before changing any labels')


if __name__=='__main__': main()
