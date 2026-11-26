"""Run the pinned AI-reviewed dev set against real PostgreSQL/pgvector and local embeddings."""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/checks"))
from app.content_authoring import digest
from app.db import connect
from app.retrieval_dev import blocking_reasons
from check_member2_ai_review import audit
from research.retrieval.metrics import aggregate, score
from research.retrieval.pgvector_dev import DevVectorStore, vector_literal

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEV = ROOT / "research/retrieval/dev/a02-e02.ai-review.v1"
CORPUS = ROOT / "content/authoring/batches/a02-e02-oatutor.v2/retrieval-dev/corpus.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class LocalEmbeddings:
    def __init__(self, cache_dir):
        from fastembed import TextEmbedding
        snapshots = list((cache_dir / "models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/snapshots").glob("*"))
        snapshots = [path for path in snapshots if (path / "model_optimized.onnx").is_file()]
        if len(snapshots) != 1:
            raise ValueError("Expected one downloaded model snapshot; see the retrieval README")
        path = snapshots[0]
        hashes = {str(file.relative_to(path)).replace("\\", "/"): file_sha256(file)
                  for file in sorted(path.rglob("*")) if file.is_file()}
        self.config = {"model": MODEL, "model_snapshot": path.name, "files_sha256": hashes,
                       "dimension": 384, "threads": 2, "provider": "CPUExecutionProvider",
                       "fastembed": version("fastembed"), "onnxruntime": version("onnxruntime"),
                       "prefix": "none", "distance": "cosine"}
        self.identity = digest(self.config)
        self.cache = ROOT / "artifacts/tooling/embedding-cache" / self.identity
        self.cache.mkdir(parents=True, exist_ok=True)
        self.model = TextEmbedding(model_name=MODEL, cache_dir=str(cache_dir), specific_model_path=str(path),
                                   threads=2, providers=["CPUExecutionProvider"])
        self.hits = self.misses = 0

    def embed(self, text):
        path = self.cache / (digest({"model": self.identity, "text": text}) + ".json")
        if path.exists():
            result = read(path)
            if result["text_sha256"] != hashlib.sha256(text.encode()).hexdigest() or result["model_id"] != self.identity:
                raise ValueError("Embedding cache provenance mismatch")
            self.hits += 1
        else:
            result = {"model_id": self.identity, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "vector": next(self.model.embed([text])).tolist()}
            write_new(path, result)
            self.misses += 1
        vector_literal(result["vector"])
        return result["vector"]


def run(model_cache):
    reviewed = audit()  # Includes every frozen pack, corpus and qrels file hash.
    corpus, queries, qrels = read(CORPUS), read(DEV / "queries.json"), read(DEV / "qrels.json")
    started = perf_counter()
    model = LocalEmbeddings(model_cache)
    model_seconds = perf_counter() - started
    vectors = {doc["content_id"]: model.embed(doc["text"]) for doc in corpus["documents"]}
    rankings = {"metadata": [], "semantic": []}
    with connect() as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        store = DevVectorStore(connection)
        store.initialize()
        sync = store.sync(corpus, digest(corpus), model.identity, vectors)
        repeat_sync = store.sync(corpus, digest(corpus), model.identity, vectors)
        database = connection.execute("SELECT version() AS version").fetchone()["version"]
        extension = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()["extversion"]
        for query in queries:
            embedding_started = perf_counter()
            vector = model.embed(query["query"])
            embedding_ms = (perf_counter() - embedding_started) * 1000
            eligible = sorted(doc["content_id"] for doc in corpus["documents"] if not blocking_reasons(doc, query))
            grades = {r["content_id"]: r["relevance"] for r in qrels if r["query_id"] == query["query_id"]}
            for mode in rankings:
                db_started = perf_counter()
                rows = store.retrieve(corpus["snapshot_id"], model.identity, query, vector,
                                      semantic=mode == "semantic", top_k=8)
                db_ms = (perf_counter() - db_started) * 1000
                ids = [row["content_id"] for row in rows]
                if sorted(ids) != eligible:
                    raise ValueError("DB metadata filters disagree with the pinned fixture")
                rankings[mode].append({"query_id": query["query_id"], "ids": ids,
                    "distances": [row["distance"] for row in rows], "eligible_candidates": len(eligible),
                    "fallback": "no_eligible_content" if not ids else None, "db_ms": db_ms,
                    "embedding_ms": embedding_ms if mode == "semantic" else 0,
                    "metrics": {str(k): score(ids, grades, k) for k in (1, 3, 5)}})
    def latency(values):
        return {"median": median(values), "p95_nearest_rank": sorted(values)[max(0, int(len(values) * .95 + .999) - 1)]}
    summary = {mode: {"cutoffs": {str(k): aggregate([r["metrics"][str(k)] for r in rows]) for k in (1, 3, 5)},
                      "fallback_count": sum(not row["ids"] for row in rows),
                      "db_latency_ms": latency([r["db_ms"] for r in rows])}
               for mode, rows in rankings.items()}
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "usage": "authoring_dev_only_not_runtime",
            "review": reviewed, "corpus_sha256": digest(corpus), "queries_sha256": digest(queries),
            "qrels_sha256": digest(qrels), "model": model.config, "model_id": model.identity,
            "postgres": database, "pgvector": extension, "sync": sync, "repeat_sync": repeat_sync,
            "model_load_seconds": model_seconds, "embedding_cache_hits": model.hits, "embedding_cache_misses": model.misses,
            "query_embedding_latency_ms": latency([r["embedding_ms"] for r in rankings["semantic"]]),
            "summary": summary, "rankings": rankings, "runtime_publication": False,
            "limitations": ["Eight draft documents and 24 AI-reviewed dev queries; no human gold or final test.",
                            "Same metadata filters for both methods. Four queries correctly return no candidates.",
                            "Recall/Hit undefined for six queries; graded nDCG undefined for four queries.",
                            "Exact scan, one local CPU/DB, no concurrent load or general performance claim.",
                            "This isolated research store is not called by the student Agent."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-local", action="store_true", help="Use the Windows validation runtime .env settings")
    parser.add_argument("--model-cache", type=Path, default=ROOT / "artifacts/tooling/embedding-models")
    args = parser.parse_args()
    if args.workspace_local:
        sys.path.insert(0, str(ROOT / "scripts/dev"))
        from validation_runtime import local_environment
        os.environ.update(local_environment())
    result = run(args.model_cache.resolve())
    path = ROOT / "artifacts/retrieval-validation" / uuid4().hex[:12] / "benchmark.json"
    write_new(path, result)
    print(json.dumps({"evidence": str(path.relative_to(ROOT)), "summary": result["summary"],
                      "repeat_sync": result["repeat_sync"]}, indent=2))


if __name__ == "__main__":
    main()
