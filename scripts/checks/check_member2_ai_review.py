"""Read-only integrity checks for delegated AI decisions and dev labels, never human approval."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.content_authoring import digest
from app.oatutor_import import file_hash, read_json, require

DEV = ROOT / "research/retrieval/dev/a02-e02.ai-review.v1"
REVIEW = DEV
SOURCE = ROOT / "content/authoring/batches/a02-e02-oatutor.v2/retrieval-dev"


def audit():
    manifest = read_json(DEV / "manifest.json")
    for key in ("input_file_sha256", "output_file_sha256"):
        for relative, expected in manifest[key].items():
            path = (ROOT / relative).resolve()
            require(path.is_relative_to(ROOT) and file_hash(path) == expected, "AI review input/output changed: " + relative)
    for name, expected in manifest["review_file_sha256"].items():
        path = REVIEW / name
        require(path.is_file() and file_hash(path) == expected, "Current AI review evidence changed: " + name)
    review, query_review = read_json(REVIEW / "review.json"), read_json(REVIEW / "query-review.json")
    require(review["original_review_files_available"] is False
            and query_review["original_review_files_available"] is False
            and review["reconstructed_on"] == "2026-11-26"
            and "reconstructed_from_retained" in review["evidence_origin"],
            "Reconstructed evidence must not be represented as the missing original review")
    require(review["review_kind"] == manifest["review_kind"] == "ai_review_for_development", "Incorrect reviewer kind")
    require(review["reviewer"] == manifest["reviewer"] == "Codex", "AI identity must stay explicit")
    require(review["independent_human_review"] is False and review["separate_independent_ai_agents"] is False
            and review["human_attestation"] is False and review["human_reviewer"] is None,
            "AI review must not claim human or multi-agent independence")
    require(review["runtime_publication"] is False and manifest["runtime_publication"] is False
            and manifest["human_approved_labels"] == 0, "AI review cannot grant runtime/human approval")
    require({d["id"] for d in review["decisions"]} == {f"M2-C0{i}" for i in range(1, 6)}
            and len(review["decisions"]) == 5
            and all(d["decision"] == "adopted_for_development" for d in review["decisions"]), "Five explicit dev decisions required")
    queries, qrels = read_json(DEV / "queries.json"), read_json(DEV / "qrels.json")
    original_queries, original_qrels = read_json(SOURCE / "queries.json"), read_json(SOURCE / "qrels.json")
    corpus = read_json(SOURCE / "corpus.json")
    require(digest(corpus) == manifest["corpus_sha256"] and digest(queries) == manifest["queries_sha256"]
            and digest(qrels) == manifest["qrels_sha256"], "AI review hash mismatch")
    require(digest(original_queries) == manifest["source_queries_sha256"]
            and digest(original_qrels) == manifest["source_qrels_sha256"], "Original label snapshot changed")
    query_ids = {q["query_id"] for q in queries}
    require(len(query_ids) == len(queries) == 24 and len(qrels) == 192, "Incomplete AI label review")
    notes = {q["query_id"]: q for q in query_review["queries"]}
    require(set(notes) == query_ids and len(query_review["queries"]) == 24
            and all(q["comment"].strip() for q in query_review["queries"]), "Review notes missing or duplicated")
    expected_keys = {(q["query_id"], d["content_id"]) for q in queries for d in corpus["documents"]}
    require({(r["query_id"], r["content_id"]) for r in qrels} == expected_keys, "Incomplete qrels matrix")
    corrections = {(q["query_id"], c["content_id"]): c for q in notes.values() for c in q["corrections"]}
    originals = {(q["query_id"], q["content_id"]): q for q in original_qrels}
    changed = set()
    for row in qrels:
        key = row["query_id"], row["content_id"]
        original = originals[key]
        require(row["label_status"] == "ai_reviewed_for_dev" and row["human_reviewed"] is False
                and row["review_id"] == review["review_id"], "Incorrect AI label provenance")
        require(type(row["relevance"]) is int and row["relevance"] in (0, 1, 2), "Invalid grade")
        require(row["authoring_eligible"] or row["relevance"] == 0, "Positive relevance on forbidden content")
        for field, value in original.items():
            if field not in ("relevance", "label_status"):
                require(row[field] == value, "AI review altered frozen eligibility/content metadata")
        if row["relevance"] != original["relevance"]:
            changed.add(key)
            require(key in corrections and corrections[key]["from"] == original["relevance"] == row["original_relevance"]
                    and corrections[key]["to"] == row["relevance"], "Grade change lacks a review reason")
    require(changed == set(corrections) and len(changed) == manifest["grade_corrections"] == 2, "Untracked label changes")
    for query, original in zip(queries, original_queries):
        require(query["query_id"] == original["query_id"] and query["label_status"] == "ai_reviewed_for_dev"
                and query["human_reviewed"] is False, "AI query provenance mismatch")
        for field, value in original.items():
            if field not in ("label_status", "label_rationale"):
                require(query[field] == value, "Query or server permissions changed during label review")
        rows = [r for r in qrels if r["query_id"] == query["query_id"]]
        require(query["ai_relevant_ids"] == [r["content_id"] for r in rows if r["relevance"] >= 1]
                and query["ai_direct_relevant_ids"] == [r["content_id"] for r in rows if r["relevance"] >= 2], "Relevance IDs mismatch")
    no_direct = [q["query_id"] for q in queries if not q["ai_direct_relevant_ids"]]
    no_gain = [q["query_id"] for q in queries if not q["ai_relevant_ids"]]
    require(manifest["recall_hit_relevance_threshold"] == 2 and manifest["ndcg_gain_by_grade"] == {"0": 0, "1": 1, "2": 3}
            and no_direct == manifest["recall_hit_no_positive_queries"] and len(no_direct) == 6
            and no_gain == manifest["ndcg_no_positive_gain_queries"] and len(no_gain) == 4,
            "Recall/Hit and graded-nDCG no-positive cases must remain separate")
    return {"dev_decisions": 5, "queries_reviewed": 24, "judgments": 192, "corrected_grades": 2,
            "recall_hit_no_positive_queries": 6, "ndcg_no_positive_gain_queries": 4,
            "human_approved_labels": 0, "runtime_publication": False,
            "review_evidence": "reconstructed_from_retained_artifacts"}


if __name__ == "__main__":
    result = audit()
    print("PASS: delegated AI dev decisions, review provenance, pinned inputs and corrected qrels")
    print(json.dumps(result, ensure_ascii=True))
