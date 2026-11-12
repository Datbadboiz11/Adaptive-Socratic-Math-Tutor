"""Explicit one-time BGE-M3 download, separate from serving API requests."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.local_embedding import MODEL_ID, MODEL_REVISION, MODEL_CACHE, load_model

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    args=parser.parse_args()
    load_model(download=True,device=args.device,cache_folder=MODEL_CACHE)
    print(json.dumps({'model':MODEL_ID,'revision':MODEL_REVISION,'cache':str(MODEL_CACHE)},ensure_ascii=False,indent=2))
