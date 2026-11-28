"""Reproducible 13-concept retrieval dev evaluation and paired product-graph outputs."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import random
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT, ROOT / "backend"):
    sys.path.insert(0, str(folder))

from app.db import connect
from app.embeddings import LocalEmbedder, vector_literal
from app.kb_cli import default_model_dir
from app.kb_projection import load_example_publications, load_profile, load_source, project
from app.kb_sync import sync_projection
from app.retrieval import KBRetriever
from research.retrieval.dataset import json_bytes, require, sha256, validate_bundle, write_new_bundle
from research.retrieval.stage6.evaluation import (
    analyze_result, grouped_summaries, paired_cluster_intervals, ranking_errors, validate_config, validate_labels,
)
from research.retrieval.stage6.paired_outputs import blind_packet, run_pairs, summarize_pairs
from scripts.checks.check_stage3_kb import isolated_acceptance_schema, make_request

CONFIG = ROOT / "research/retrieval/stage6/member2-13.config.v1.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_inputs(config):
    validate_config(config)
    stage5_path = (ROOT / config["unjudged_dev"]).resolve()
    legacy_path = (ROOT / config["labelled_dev"]).resolve()
    require(stage5_path.is_relative_to(ROOT) and legacy_path.is_relative_to(ROOT), "Dataset escapes workspace")
    manifest, corpus, queries, qrels = validate_bundle(stage5_path, ROOT)
    require(manifest["owner"] == "Member 2" and manifest["concept_count"] == 13
            and manifest["missing_content_queries"] == 0, "Stage 6 needs the ready Member 2 workset")
    assigned = set(manifest["concept_ids"])
    require({q["concept_id"] for q in queries} == assigned and all(q["split"] == "dev" for q in queries),
            "Foreign concept or non-dev query in scoped workset")
    validate_labels(queries, qrels, unjudged=True)
    legacy = read(legacy_path / "manifest.json")
    require(legacy["label_review"] == "deterministic_development_labels_not_independent_human_gold",
            "Unexpected historical label provenance")
    require(set(legacy["concept_ids"]) == assigned and legacy["snapshot_id"] == corpus["snapshot_id"],
            "Comparator datasets do not share the thirteen-concept snapshot")
    for name, expected in legacy["output_file_sha256"].items():
        require(sha256((legacy_path / name).read_bytes()) == expected, "Legacy dataset hash mismatch")
    old_queries, old_qrels = read(legacy_path / "queries.json"), read(legacy_path / "qrels.json")
    require(read(legacy_path / "corpus.json") == corpus, "Comparator corpora differ")
    require({q["concept_id"] for q in old_queries} == assigned, "Foreign legacy query")
    old_labels = validate_labels(old_queries, old_qrels, unjudged=False)
    cohorts = [{"name": "labelled_dev_104", "queries": old_queries, "labels": old_labels,
                "label_origin": legacy["label_review"]},
               {"name": "unjudged_dev_156", "queries": queries, "labels": None,
                "label_origin": "unjudged_pending_independent_review"}]
    return manifest, corpus, cohorts


def input_hashes(config_path, config):
    names = ["research/retrieval/stage6/evaluation.py", "research/retrieval/stage6/paired_outputs.py",
             "research/retrieval/stage6/ratings.py", "scripts/retrieval/review_member2_stage6.py",
             "scripts/retrieval/run_member2_stage6.py", "scripts/checks/check_stage3_kb.py",
             "backend/app/retrieval.py", "backend/app/embeddings.py", "backend/app/kb_sync.py",
             "backend/app/kb_contracts.py", "backend/app/kb_projection.py", "backend/app/teaching_runtime.py",
             "backend/app/tutor.py", "backend/app/member2_runtime.py", "backend/app/math_validator.py",
             "research/retrieval/metrics.py", "research/retrieval/dataset.py", "content/kb/embedding-profile.v1.json"]
    paths = {str((ROOT / name).relative_to(ROOT)): ROOT / name for name in names}
    paths[config_path.resolve().relative_to(ROOT).as_posix()] = config_path
    for folder, suffix in ((ROOT / "backend/app", "*.py"), (ROOT / "backend/migrations", "*.sql")):
        for path in folder.rglob(suffix):
            paths[path.relative_to(ROOT).as_posix()] = path
    for path in (ROOT / "backend").glob("requirements*.txt"):
        paths[path.relative_to(ROOT).as_posix()] = path
    paths["scripts/dev/validation_runtime.py"] = ROOT / "scripts/dev/validation_runtime.py"
    for folder_name in (config["labelled_dev"], config["unjudged_dev"]):
        folder = ROOT / folder_name
        manifest = read(folder / "manifest.json")
        for name in ["manifest.json", *manifest.get("files_sha256", manifest.get("output_file_sha256", {}))]:
            paths[(folder / name).relative_to(ROOT).as_posix()] = folder / name
        for name in manifest.get("source_sha256", manifest.get("source_file_sha256", {})):
            paths[name] = ROOT / name
    return {name: sha256(path.read_bytes()) for name, path in sorted(paths.items())}


def run_retrieval(cohorts, projection, embedder, config, progress):
    retriever = KBRetriever(embedder)
    rows, cache = [], []
    for cohort_index, cohort in enumerate(cohorts):
        embedder._cached_query.cache_clear()
        for repeat in range(config["warm_repeats"] + 1):
            phase = "query_cache_cold_model_warm" if repeat == 0 else "query_cache_warm"
            rng = random.Random(config["seed"] + cohort_index * 100 + repeat)
            order = list(cohort["queries"])
            rng.shuffle(order)
            for query in order:
                methods = list(config["methods"])
                rng.shuffle(methods)
                for method in methods:
                    if query.get("expected_route") in ("clarify", "out_of_scope"):
                        rows.append({"dataset": cohort["name"], "query_id": query["query_id"],
                            "concept_id": query["concept_id"], "purpose": query["purpose"], "phase": phase,
                            "repeat": repeat, "method": method, "executed": False,
                            "expected_route": query["expected_route"], "metrics": None,
                            "note": "Annotated pre-retrieval route; no classifier accuracy claim"})
                        continue
                    before = embedder.calls
                    started = perf_counter()
                    result = retriever.retrieve(make_request(projection, query, method))
                    elapsed = (perf_counter() - started) * 1000
                    labels = cohort["labels"][query["query_id"]] if cohort["labels"] is not None else None
                    row = analyze_result(query, result, wall_ms=elapsed, embedding_calls=embedder.calls - before,
                        phase=phase, repeat=repeat, dataset=cohort["name"], labels=labels)
                    rows.append(row)
            info = embedder._cached_query.cache_info()
            cache.append({"dataset": cohort["name"], "phase": phase, "repeat": repeat, **info._asdict()})
            if repeat:
                require(not any(row["embedding_texts_computed"] for row in rows if row["dataset"] == cohort["name"]
                                and row["repeat"] == repeat and row["executed"]), "Warm queries recomputed embeddings")
            progress({"stage": "retrieval", "dataset": cohort["name"], "phase": phase, "repeat": repeat})
    for cohort in cohorts:
        for method in config["methods"]:
            baseline = {row["query_id"]: row["ids"] for row in rows if row["dataset"] == cohort["name"]
                        and row["method"] == method and row["repeat"] == 0 and row["executed"]}
            require(all(row["ids"] == baseline[row["query_id"]] for row in rows if row["dataset"] == cohort["name"]
                        and row["method"] == method and row["executed"]), "Cache passes changed rankings")
    return rows, cache


def direct_probes(cohort, projection, embedder):
    rows = []
    retriever = KBRetriever(embedder)
    for query in cohort["queries"]:
        if not (query["query_id"].endswith("EXPLANATION") or query["query_id"].endswith("HINT-1")):
            continue
        content_id = query["concept_id"] + ("-explanation" if query["purpose"] == "explanation" else "-hint-1")
        before = embedder.calls
        result = retriever.retrieve(make_request(projection, query, "direct", {
            "content_id": content_id, "content_version": projection.registry.content_version}))
        require([chunk.content_id for chunk in result.chunks] == [content_id] and before == embedder.calls,
                "Direct lookup failed or called embedding")
        rows.append({"query_id": query["query_id"], "content_id": content_id, "embedding_texts_computed": 0,
                     "retrieval_core_ms": result.elapsed_ms, "quality_aggregation": "excluded_id_lookup"})
    require(len(rows) == 26, "Expected separate explanation/hint ID probes for all thirteen concepts")
    return rows


def query_plans(query, projection, embedder):
    plans = {}
    vector = vector_literal(embedder.embed_query(query["query"]))
    for method in ("metadata", "semantic"):
        request = make_request(projection, query, method)
        where, params = KBRetriever._filters(request)
        if method == "semantic":
            selection = "SELECT ch.content_id,e.embedding OPERATOR(public.<=>) %s::public.vector AS distance"
            params = [vector, *params]
            ordering = " ORDER BY distance,ch.content_id,ch.content_version LIMIT 5"
        else:
            selection = "SELECT ch.content_id"
            ordering = " ORDER BY ch.content_id,ch.content_version LIMIT 5"
        with connect() as connection:
            connection.execute("SET LOCAL statement_timeout='2500ms'")
            plans[method] = connection.execute("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + selection + where + ordering,
                                               params).fetchone()["QUERY PLAN"]
    return {"query_id": query["query_id"], "eligible_candidates": len(query["eligible_candidate_ids"]), "plans": plans}


def markdown_report(report):
    lines = ["# Chặng 6 — Kết quả dev trên 13 concept Member 2", "",
             "Nhãn 104 query là nhãn phát triển tất định. Bộ 156 query chưa có nhãn xác nhận; "
             "không tính chất lượng trên bộ này. Chưa phải nghiệm thu RQ3 chính thức.", "",
             "| Dataset | Cách lấy | Cache query | nDCG@1 | nDCG@3 | Recall@5 | p95 wall (ms) |",
             "|---|---|---|---:|---:|---:|---:|"]
    for group in report["retrieval"]:
        summary = group["summary"]
        cutoffs = summary["cutoffs"]
        values = [cutoffs["1"]["ndcg"]["mean"], cutoffs["3"]["ndcg"]["mean"], cutoffs["5"]["recall"]["mean"]] if cutoffs else [None] * 3
        text = ["N/A" if value is None else f"{value:.4f}" for value in values]
        lines.append(f"| {group['dataset']} | {group['method']} | {group['phase']} | "
                     + " | ".join(text) + f" | {summary['wall_ms']['p95']:.2f} |")
    lines += ["", "## Diễn giải", "",
              "- Direct lookup được báo riêng, không trộn vào điểm semantic.",
              "- K=5 bao phủ toàn bộ tập ứng viên nhỏ; xem thêm K=1/3 và nDCG để phân biệt ranking.",
              "- Query-cache cold chạy sau khi model/corpus đã được làm nóng; không phải process cold start.",
              "- Warm pass dùng cache vector hiện hữu; vẫn kiểm đầy đủ scope/review/exclusion trong mỗi request.",
              "- p95 là retrieval tuần tự có ghi trace, không phải p95 toàn lượt gia sư hoặc thử tải đồng thời.",
              "- Ca mơ hồ/ngoài scope của bộ 156 query chưa chạy classifier: chỉ là route được soạn trước.",
              "- Khoảng tin cậy bootstrap lấy mẫu theo concept, chỉ mô tả độ nhạy của dev labels.",
              "- Chưa thêm ANN/hybrid/reranker; phân tích lỗi dev được lưu để quyết định bước tiếp theo.", "",
              "## Full / No-RAG", "", json.dumps(report["paired_outputs"], ensure_ascii=False, indent=2), "",
              "Đọc `paired-blind.json` để chấm; giữ `paired-key.json` tách khỏi người chấm. "
              "Ẩn tên cấu hình không bảo đảm người chấm không suy đoán được từ nội dung. "
              "Không coi số đầu ra khác nhau là bằng chứng Full có chất lượng dạy học tốt hơn.", ""]
    return "\n".join(lines).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--workspace-local", action="store_true")
    parser.add_argument("--audit-only", action="store_true", help="Validate inputs without DB or inference")
    parser.add_argument("--output", type=Path, help="New result directory; existing paths are refused")
    args = parser.parse_args()
    try:
        config = read(args.config)
        manifest, corpus, cohorts = load_inputs(config)
        sources = input_hashes(args.config, config)
        if args.audit_only:
            print(json.dumps({"status": "passed", "owner": "Member 2", "concepts": 13,
                "labelled_dev_queries": len(cohorts[0]["queries"]), "unjudged_dev_queries": len(cohorts[1]["queries"]),
                "formal_test_ready": False, "model_api_calls": 0}))
            return 0
        run_id = uuid4().hex[:12]
        output = args.output or ROOT / "artifacts/stage6-validation" / run_id
        require(not output.exists(), "Result directory already exists; use a new destination")
        if args.workspace_local:
            from scripts.dev.validation_runtime import local_environment
            os.environ.update(local_environment())
        for name in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(name, None)
        os.environ.update(LLM_ENABLED="false", AUTHORING_LLM_ENABLED="false")
        profile = load_profile()
        registry, bank, origin = load_source(config["corpus_source"])
        projection = project(registry, bank, profile, origin=origin, examples=load_example_publications("member2-v2"))
        require(projection.snapshot_id == corpus["snapshot_id"], "Research and production projection differ")
        embedder = LocalEmbedder(profile, default_model_dir(profile))
        progress = lambda value: print(json.dumps(value), flush=True)
        with isolated_acceptance_schema(run_id) as isolation:
            started = perf_counter()
            embedder._load()
            model_load_ms = (perf_counter() - started) * 1000
            first_sync = sync_projection(projection, embedder, activate=True)
            repeat_sync = sync_projection(projection, embedder, activate=True)
            require(repeat_sync["computed_embeddings"] == 0, "Repeat sync recomputed corpus embeddings")
            progress({"stage": "corpus_ready", "chunks": len(projection.chunks)})
            direct = direct_probes(cohorts[0], projection, embedder)
            rows, cache = run_retrieval(cohorts, projection, embedder, config, progress)
            plans = query_plans(next(query for query in cohorts[0]["queries"] if len(query["eligible_candidate_ids"]) == 3), projection, embedder)
            checkpoint = json_bytes({"status": "retrieval_completed_pairs_pending", "run_id": run_id,
                "formal_test_ready": False, "config": config, "source_sha256": sources,
                "snapshot_id": projection.snapshot_id, "rankings": rows, "cache": cache,
                "direct_lookup_probes": direct, "query_plans": plans})
            write_new_bundle(output, {"retrieval-checkpoint.json": checkpoint})
            progress({"stage": "retrieval_checkpoint_saved", "output": str(output)})
            pairs = run_pairs(bank, projection.snapshot_id, progress)
            with connect() as connection:
                traces = connection.execute("SELECT * FROM kb_retrieval_traces ORDER BY created_at,retrieval_id").fetchall()
                pg = connection.execute("SELECT version() AS version").fetchone()["version"]
                vector_version = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()["extversion"]
        require(input_hashes(args.config, config) == sources, "Source files changed while the run was in progress")
        public, key, rating = blind_packet(pairs, config["seed"])
        summaries = grouped_summaries(rows)
        labelled_rows = [row for row in rows if row["dataset"] == cohorts[0]["name"]]
        report = {"status": "dev_evaluation_completed", "formal_test_ready": False, "run_id": run_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(), "owner": "Member 2", "concept_ids": manifest["concept_ids"],
            "snapshot_id": projection.snapshot_id, "embedding_profile": profile.model_dump(mode="json"),
            "model_load_ms": model_load_ms, "model_api_calls": 0, "local_embedding_texts_computed": embedder.calls,
            "retrieval": summaries, "paired_cluster_intervals": paired_cluster_intervals(labelled_rows,
                config["bootstrap_samples"], config["seed"]), "direct_lookup_probes": direct,
            "paired_outputs": summarize_pairs(pairs), "cache": cache,
            "sync": {"first": first_sync, "repeat": repeat_sync}, "isolation": isolation,
            "environment": {"python": sys.version, "platform": platform.platform(), "postgres": pg,
                            "pgvector": vector_version, "packages": {name: version(name) for name in
                                ("psycopg", "fastembed", "onnxruntime", "langgraph")}},
            "pending_formal_evidence": ["independent_relevance_labels", "independent_paired_quality_ratings",
                                        "independent_test_scenarios_and_frozen_inputs", "remote_ci_and_load_evidence"]}
        files = {"config.json": json_bytes(config), "inputs.json": json_bytes(sources), "report.json": json_bytes(report),
            "rankings.json": json_bytes(rows), "query-plans.json": json_bytes(plans),
            "retrieval-traces.json": json_bytes(json.loads(json.dumps(traces, default=str))),
            "ranking-errors.json": json_bytes(ranking_errors(labelled_rows, cohorts[0]["queries"], cohorts[0]["labels"])),
            "paired-raw.json": json_bytes(pairs), "paired-blind.json": json_bytes(public), "paired-key.json": json_bytes(key),
            "paired-review-A.template.json": json_bytes(rating), "paired-review-B.template.json": json_bytes(deepcopy(rating)),
            "report.md": markdown_report(report)}
        files["manifest.json"] = json_bytes({"run_id": run_id, "status": report["status"], "formal_test_ready": False,
            "files_sha256": {"retrieval-checkpoint.json": sha256(checkpoint),
                             **{name: sha256(content) for name, content in files.items()}}})
        write_new_bundle(output, files)
        print(json.dumps({"status": report["status"], "output": str(output), "formal_test_ready": False,
                          "paired_scenarios": len(pairs), "model_api_calls": 0}), flush=True)
        return 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, "Stage 6 evaluation failed: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
