"""Dev-only retrieval analysis. Unknown relevance is never a zero or a successful fallback."""
from collections import Counter, defaultdict
import math
import random
from statistics import mean

from research.retrieval.dataset import require
from research.retrieval.metrics import aggregate, score


def validate_config(config):
    require(config["protocol_version"] == "member2-stage6-dev-1.0.0", "Unknown Stage 6 protocol")
    require(config["owner"] == "Member 2" and config["formal_test"] is False, "This runner is dev-only")
    require(config["methods"] == ["metadata", "semantic"], "Comparators must share the production filters")
    require(config["cutoffs"] == [1, 3, 5] and config["top_k"] == 5, "Cutoffs must stay pinned")
    require(config["relevance_threshold"] == 2 and config["ndcg_gain_by_grade"] == {"0": 0, "1": 1, "2": 3},
            "Metric definitions differ from the pinned dev protocol")
    require(type(config["warm_repeats"]) is int and 1 <= config["warm_repeats"] <= 5, "Invalid repeat budget")
    require(type(config["bootstrap_samples"]) is int and 100 <= config["bootstrap_samples"] <= 10000,
            "Invalid bootstrap budget")
    require(type(config["seed"]) is int and config["bootstrap_cluster"] == "concept_id", "Invalid grouping/seed")
    return config


def quantile(values, probability):
    if not values:
        return None
    require(0 <= probability <= 1 and all(math.isfinite(value) for value in values), "Invalid percentile input")
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def validate_labels(queries, qrels, *, unjudged):
    query_map = {query["query_id"]: query for query in queries}
    require(len(query_map) == len(queries), "Duplicate benchmark query")
    expected = {(query["query_id"], content_id) for query in queries for content_id in query["eligible_candidate_ids"]}
    labels = {query_id: {} for query_id in query_map}
    seen = set()
    for row in qrels:
        key = row["query_id"], row["content_id"]
        require(key in expected and key not in seen, "Forbidden, unknown or duplicate relevance row")
        grade = row["relevance"]
        require(grade is None if unjudged else type(grade) is int and grade in (0, 1, 2),
                "Unknown labels cannot become quality evidence")
        seen.add(key)
        labels[key[0]][key[1]] = grade
    require(seen == expected, "Qrels must cover all eligible candidates, not only a ranking pool")
    return labels


def analyze_result(query, result, *, wall_ms, embedding_calls, phase, repeat, dataset, labels):
    ids = [chunk.content_id for chunk in result.chunks]
    expected = set(query["eligible_candidate_ids"])
    require(len(ids) == len(set(ids)), "Duplicate result even in an unjudged cohort")
    require(result.fallback_reason in (None, "no_eligible_content"), "Retriever failed rather than returning a valid fallback")
    require(set(ids).issubset(expected) and len(ids) == min(5, len(expected)), "Runtime scope/coverage mismatch")
    require(result.eligible_count == len(expected), "Runtime candidate count disagrees with pinned scope")
    require(bool(ids) == bool(expected), "Empty fallback mismatch")
    judged = labels is not None
    return {"dataset": dataset, "query_id": query["query_id"], "concept_id": query["concept_id"],
            "purpose": query["purpose"], "intent_group": query.get("intent_group", query["concept_id"]),
            "expected_route": query.get("expected_route", "retrieve" if expected else "empty"),
            "phase": phase, "repeat": repeat, "method": result.method, "executed": True,
            "request_id": str(result.request_id), "retrieval_id": str(result.retrieval_id),
            "ids": ids, "eligible_count": len(expected), "fallback_reason": result.fallback_reason,
            "wall_ms": wall_ms, "retrieval_core_ms": result.elapsed_ms, "embedding_texts_computed": embedding_calls,
            "scope_violations": 0,
            "metrics": {str(k): score(ids, labels, k) for k in (1, 3, 5)} if judged else None}


def summarize(rows):
    executed = [row for row in rows if row["executed"]]
    unique = list({row["query_id"]: row for row in executed}.values())
    labelled = [row for row in unique if row["metrics"] is not None]
    timing = [row["wall_ms"] for row in executed]
    empty = [row for row in executed if row["expected_route"] == "empty"]
    return {"rows": len(rows), "executed_requests": len(executed), "unique_queries": len(unique),
            "route_controls_not_executed": len(rows) - len(executed),
            "quality_labelled_queries": len(labelled), "unjudged_queries": len(unique) - len(labelled),
            "cutoffs": {str(k): aggregate([row["metrics"][str(k)] for row in labelled]) for k in (1, 3, 5)} if labelled else None,
            "quality_note": "deterministic_dev_labels_not_human_gold" if labelled else "unjudged_no_quality_claim",
            "wall_ms": {"p50": quantile(timing, .5), "p95": quantile(timing, .95), "samples": len(timing)},
            "embedding_texts_computed": sum(row.get("embedding_texts_computed", 0) for row in rows),
            "candidate_counts": dict(sorted(Counter(row["eligible_count"] for row in executed).items())),
            "all_candidates_fit_at_5": all(row["eligible_count"] <= 5 for row in executed),
            "empty_controls": {"unique_queries": len({row["query_id"] for row in empty}),
                               "requests": len(empty), "returned_empty": sum(not row["ids"] for row in empty)},
            "scope_violations": sum(row.get("scope_violations", 0) for row in executed)}


def grouped_summaries(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["dataset"], row["method"], row["phase"])].append(row)
    return [{"dataset": dataset, "method": method, "phase": phase, "summary": summarize(selected),
             "by_concept": {cid: summarize([row for row in selected if row["concept_id"] == cid])
                            for cid in sorted({row["concept_id"] for row in selected})},
             "by_purpose": {purpose: summarize([row for row in selected if row["purpose"] == purpose])
                            for purpose in sorted({row["purpose"] for row in selected})}}
            for (dataset, method, phase), selected in sorted(groups.items())]


def paired_cluster_intervals(rows, samples, seed):
    """Resample whole concepts; paraphrases within a concept are never independent draws."""
    selected = [row for row in rows if row["executed"] and row["phase"] == "query_cache_cold_model_warm"
                and row["metrics"] is not None]
    mapped = {(row["query_id"], row["method"]): row for row in selected}
    output = {}
    for cutoff in (1, 3, 5):
        for metric in ("recall", "hit", "ndcg"):
            clusters = defaultdict(list)
            for row in selected:
                if row["method"] != "metadata":
                    continue
                other = mapped.get((row["query_id"], "semantic"))
                require(other is not None, "Incomplete paired comparison")
                left, right = row["metrics"][str(cutoff)][metric], other["metrics"][str(cutoff)][metric]
                if left is not None and right is not None:
                    clusters[row["concept_id"]].append(right - left)
            keys = sorted(clusters)
            rng = random.Random(seed)
            draws = [mean(value for _ in keys for value in clusters[rng.choice(keys)]) for _ in range(samples)] if keys else []
            values = [value for group in clusters.values() for value in group]
            output[f"{metric}@{cutoff}"] = {"semantic_minus_metadata": mean(values) if values else None,
                "ci95": [quantile(draws, .025), quantile(draws, .975)], "concept_clusters": len(keys),
                "defined_queries": len(values), "bootstrap_samples": samples,
                "interpretation": "dev_sensitivity_only_not_population_or_human_gold_inference"}
    return output


def ranking_errors(rows, queries, labels):
    query_map = {query["query_id"]: query for query in queries}
    errors = []
    for row in rows:
        if not row["executed"] or row["metrics"] is None or row["phase"] != "query_cache_cold_model_warm":
            continue
        direct = {cid for cid, grade in labels[row["query_id"]].items() if grade == 2}
        if direct and (not row["ids"] or row["ids"][0] not in direct):
            errors.append({"method": row["method"], "query_id": row["query_id"], "concept_id": row["concept_id"],
                "purpose": row["purpose"], "query": query_map[row["query_id"]]["query"], "ranking": row["ids"],
                "relevant_grade_2": sorted(direct), "ndcg_at_1": row["metrics"]["1"]["ndcg"]})
    return errors
