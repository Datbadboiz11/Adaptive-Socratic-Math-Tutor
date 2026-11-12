"""Offline grounding demo and explicit, non-destructive Neo4j registry import."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.curriculum import load_curriculum
from app.curriculum_graph import Neo4jGraph, GraphUnavailable
from app.pilot_grounding import ground
from app.retrieval_contracts import GroundingSubmission


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--import-neo4j',action='store_true')
    parser.add_argument('--problem')
    parser.add_argument('--step',action='append')
    parser.add_argument('--kind',choices=['steps','final_answer'],default='steps')
    parser.add_argument('--method',choices=['metadata','lexical','semantic'],default='semantic')
    parser.add_argument('--graph',choices=['registry','neo4j'],default='neo4j')
    parser.add_argument('--hint-level',type=int,default=1)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    registry,bank=load_curriculum()
    if args.import_neo4j:
        try:
            result=Neo4jGraph().import_registry(registry)
        except GraphUnavailable as error:
            raise SystemExit(str(error)) from None
    else:
        if not args.problem or not args.step:
            parser.error('Specify --problem and one or more --step, or --import-neo4j')
        pair=next(((pack,p) for pack in bank.packs for p in pack.problems if p.case_id==args.problem),None)
        if pair is None:
            parser.error('Unknown pilot problem')
        pack,problem=pair
        result=ground(registry,bank,pack,problem,GroundingSubmission(submission_kind=args.kind,steps=args.step,
                      method=args.method,hint_level=args.hint_level),provider=args.graph).model_dump(mode='json')
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
