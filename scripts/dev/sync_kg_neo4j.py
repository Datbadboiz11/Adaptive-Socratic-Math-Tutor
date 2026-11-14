"""Đồng bộ Knowledge Graph từ registry sang Neo4j rồi đối chiếu kết quả truy vấn.

    docker compose --profile kg up -d neo4j
    python scripts/dev/sync_kg_neo4j.py                # kiểm tra registry → ghi Neo4j → đối chiếu
    python scripts/dev/sync_kg_neo4j.py --verify-only  # chỉ đối chiếu, không ghi

Kết nối đọc từ biến môi trường NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD (và file .env nếu có);
mặc định khớp service ``neo4j`` trong compose.yaml. Registry có lỗi thì không ghi gì.
"""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.kg.graph import GraphInvalid, KnowledgeGraph  # noqa: E402
from app.kg.neo4j_store import DEFAULT_URI, Neo4jGraph  # noqa: E402


def env_with_dotenv() -> dict:
    values = {}
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    if "NEO4J_URI" not in values and "NEO4J_BOLT_PORT" in values:
        values["NEO4J_URI"] = f"bolt://127.0.0.1:{values['NEO4J_BOLT_PORT']}"
    return {"NEO4J_URI": DEFAULT_URI, **values, **os.environ}


def mismatches(graph: KnowledgeGraph, store: Neo4jGraph) -> list[str]:
    """So từng concept ở cả hai chế độ (chỉ cạnh đã duyệt / kể cả nháp) giữa Neo4j và file."""
    out = []
    for concept_id in graph.concepts:
        for drafts in (False, True):
            if store.neighbourhood(concept_id, include_drafts=drafts) != \
                    graph.neighbourhood(concept_id, include_drafts=drafts):
                out.append(f"{concept_id} (include_drafts={drafts})")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        graph = KnowledgeGraph.load()
    except GraphInvalid as error:
        for issue in error.issues:
            print(f"LỖI {issue.code}: {issue.message}")
        print("FAIL: registry có lỗi, không đồng bộ")
        return 1
    store = Neo4jGraph.from_env(env_with_dotenv(), timeout=10.0)
    try:
        if not args.verify_only:
            meta = store.sync(graph)
            print(f"Đã ghi {meta['concepts']} concept, {meta['edges']} cạnh; phiên bản {graph.version}")
        meta = store.meta()
        if meta is None or meta["fingerprint"] != graph.fingerprint:
            print("FAIL: Neo4j chưa đồng bộ bản registry hiện tại; chạy lại không kèm --verify-only")
            return 1
        different = mismatches(graph, store)
    finally:
        store.close()
    if different:
        print("FAIL: kết quả Neo4j khác bản đọc từ file ở: " + ", ".join(different))
        return 1
    print(f"PASS: Neo4j khớp registry trên {len(graph.concepts)} concept, cả hai chế độ duyệt")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
