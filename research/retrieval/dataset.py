"""Offline relevance worksets: unknown labels stay unknown; reviews pin exact bytes."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unicodedata

from app.kb_contracts import KBChunk


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def blocking_reasons(document, query):
    """The same publication and scope boundaries used by the serving retriever."""
    reasons = []
    for name, invalid in (
        ("review", document["review"]["status"] != "human_approved"),
        ("concept_skill", document["concept_id"] != query["concept_id"]
         or query["target_skill_id"] not in document["skill_ids"]),
        ("purpose", document["kind"] != query["purpose"]),
        ("hint_level", document["hint_level"] > query["allowed_hint_level"]),
        ("grade", not set(document["grade_levels"]).intersection(query["grade_levels"])),
        ("difficulty", document["difficulty"] is not None and document["difficulty"] != query["difficulty"]),
        ("active_problem", document["problem_id"] is not None
         and document["problem_id"] == query["active_problem_id"]),
        ("source_group", document["source_group"] is not None
         and document["source_group"] in query["excluded_source_groups"]),
        ("family", document["kind"] == "example" and document["family_id"] in query["excluded_family_ids"]),
        ("lineage", document["kind"] == "example"
         and bool(set(document["lineage_ids"]).intersection(query["excluded_lineage_ids"]))),
    ):
        if invalid:
            reasons.append(name)
    return reasons


def audit_splits(queries, reserved_dev_concepts=()):
    """Hold a concept and every linked intent/source/family wholly in one split."""
    seen_ids, texts, groups = set(), {}, {}
    for query in queries:
        qid, split = query["query_id"], query["split"]
        require(qid not in seen_ids, "Duplicate query ID: " + qid)
        seen_ids.add(qid)
        require(split in ("dev", "test_candidate"), "Unknown split")
        require(split == "dev" or query["concept_id"] not in reserved_dev_concepts,
                "Historical dev concept leaked into test: " + qid)
        key = normalized(query["query"])
        require(key and key not in texts, "Duplicate normalized query text: " + qid)
        texts[key] = split
        lineage = ["concept:" + query["concept_id"], "intent:" + query["intent_group"],
                   *["lineage:" + value for field in ("excluded_source_groups", "excluded_family_ids", "excluded_lineage_ids")
                     for value in query[field]]]
        for group in lineage:
            require(group not in groups or groups[group] == split, "Cross-split lineage: " + group)
            groups[group] = split
    return dict(sorted(Counter(q["split"] for q in queries).items()))


def make_workset(corpus, queries):
    documents = {doc["content_id"]: doc for doc in corpus["documents"]}
    require(len(documents) == len(corpus["documents"]), "Duplicate corpus document")
    for document in documents.values():
        require(document["review"]["status"] == "human_approved", "Corpus contains unpublished content")
        KBChunk.model_validate(document)
    qrels = []
    for query in queries:
        require(query["purpose"] in ("explanation", "hint", "example"), "Unknown retrieval purpose")
        require(type(query["allowed_hint_level"]) is int and 0 <= query["allowed_hint_level"] <= 3,
                "Invalid hint permission")
        require(query["expected_route"] in ("retrieve", "empty", "clarify", "out_of_scope"), "Unknown route")
        require(query["content_status"] in ("ready", "awaiting_reviewed_content"), "Unknown content status")
        require(query["snapshot_id"] == corpus["snapshot_id"], "Query snapshot mismatch")
        require(isinstance(query["query"], str) and 0 < len(query["query"].strip()) <= 2000, "Invalid query text")
        require(query["grade_levels"] and all(type(g) is int and 6 <= g <= 12 for g in query["grade_levels"]),
                "Invalid grade scope")
        for field in ("excluded_source_groups", "excluded_family_ids", "excluded_lineage_ids"):
            values = query[field]
            require(isinstance(values, list) and all(isinstance(value, str) and value for value in values)
                    and len(set(values)) == len(values), "Invalid exclusion scope")
        available = any(doc["concept_id"] == query["concept_id"] for doc in documents.values())
        require((query["content_status"] == "ready") == available, "Content readiness differs from corpus")
        if available:
            require(any(doc["concept_id"] == query["concept_id"] and query["target_skill_id"] in doc["skill_ids"]
                        for doc in documents.values()), "Unknown concept/skill scope")
        eligible = sorted(doc_id for doc_id, doc in documents.items() if not blocking_reasons(doc, query))
        # Clarification/out-of-scope decisions precede retrieval; they are not
        # successful ranking queries or no-positive retrieval measurements.
        query["eligible_candidate_ids"] = eligible if query["expected_route"] in ("retrieve", "empty") else []
        if query["content_status"] == "awaiting_reviewed_content":
            require(not eligible, "Missing-content query unexpectedly has serving content")
        if query["expected_route"] == "empty" and query["content_status"] == "ready":
            require(not eligible, "Empty control still has eligible content")
        for content_id in query["eligible_candidate_ids"]:
            document = documents[content_id]
            qrels.append({"query_id": query["query_id"], "content_id": content_id,
                          "content_version": document["content_version"],
                          "content_sha256": sha256(json_bytes(document)),
                          "relevance": None, "label_status": "unjudged"})
    return qrels


def review_template(dataset_id, corpus_hash, queries_hash, queries, qrels, query_ids, slot):
    wanted = set(query_ids)
    require(wanted and wanted.issubset({q["query_id"] for q in queries}), "Invalid review selection")
    return {"schema_version": "1.0.0", "dataset_id": dataset_id, "slot": slot,
            "corpus_sha256": corpus_hash, "queries_sha256": queries_hash,
            "reviewer": None, "reviewed_at": None, "method": "independent_human",
            "queries": [{"query_id": q["query_id"], "checked": False,
                         "query_accepted": None, "notes": ""} for q in queries if q["query_id"] in wanted],
            "judgments": [dict(row) for row in qrels if row["query_id"] in wanted]}


def validate_bundle(base, root=None):
    base = Path(base)
    read = lambda name: json.loads((base / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")
    require(manifest["status"] == "candidate_pending_content_and_independent_review",
            "The starter bundle cannot claim a frozen or reviewed test")
    require({"corpus.json", "queries.json", "qrels.unjudged.json", "coverage.json",
             "pilot-review-A.template.json", "pilot-review-B.template.json"}.issubset(manifest["files_sha256"]),
            "Manifest must pin every required workset file")
    for name, expected in manifest["files_sha256"].items():
        target = (base / name).resolve()
        require(target.is_relative_to(base.resolve()) and target.is_file(), "Invalid bundle path")
        require(sha256(target.read_bytes()) == expected, "Dataset file hash mismatch: " + name)
    if root is not None:
        root = Path(root).resolve()
        for name, expected in manifest["source_sha256"].items():
            target = (root / name).resolve()
            require(target.is_relative_to(root) and target.is_file(), "Invalid source path")
            require(sha256(target.read_bytes()) == expected, "Dataset source hash mismatch: " + name)
    corpus, queries, qrels = read("corpus.json"), read("queries.json"), read("qrels.unjudged.json")
    require(corpus["snapshot_id"] == manifest["snapshot_id"], "Snapshot mismatch")
    splits = audit_splits(queries, manifest["reserved_dev_concepts"])
    original = json_bytes(queries)
    expected_qrels = make_workset(corpus, queries)
    require(json_bytes(queries) == original, "Candidate sets do not match the pinned corpus")
    require(qrels == expected_qrels, "Unjudged workset differs from eligible document versions")
    require(len(queries) == manifest["query_count"] and len(qrels) == manifest["judgment_count"],
            "Manifest count mismatch")
    require(len(corpus["documents"]) == manifest["document_count"], "Document count mismatch")
    concepts = {q["concept_id"] for q in queries}
    require(len(concepts) == manifest["concept_count"], "Concept count mismatch")
    require(splits == manifest["split_counts"], "Split count mismatch")
    return manifest, corpus, queries, qrels


def validate_review(review, manifest, queries, qrels):
    require(review["dataset_id"] == manifest["dataset_id"], "Review belongs to another dataset")
    for key, name in (("corpus_sha256", "corpus.json"), ("queries_sha256", "queries.json")):
        require(review[key] == manifest["files_sha256"][name], "Stale review: " + key)
    require(review["method"] == "independent_human", "Independent human review required")
    reviewer = review["reviewer"]
    require(isinstance(reviewer, str) and bool(normalized(reviewer)), "Real reviewer identity required")
    require(isinstance(review["reviewed_at"], str), "Review timestamp required")
    timestamp = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    require(timestamp.tzinfo is not None and timestamp <= datetime.now(timezone.utc), "Invalid review timestamp")
    selected = {row["query_id"] for row in review["queries"]}
    query_map = {row["query_id"]: row for row in queries}
    require(selected and len(selected) == len(review["queries"]) and selected.issubset(query_map),
            "Unknown or duplicate reviewed query")
    for row in review["queries"]:
        require(row["checked"] is True and row["query_accepted"] is True, "Query review is incomplete or rejected")
        require(query_map[row["query_id"]]["content_status"] == "ready", "Content not ready for review")
    expected = {(row["query_id"], row["content_id"]): row for row in qrels if row["query_id"] in selected}
    labels = {}
    for row in review["judgments"]:
        key = row["query_id"], row["content_id"]
        require(key in expected and key not in labels, "Unknown, forbidden or duplicate judgment")
        require(type(row["relevance"]) is int and row["relevance"] in (0, 1, 2), "Unjudged or invalid relevance")
        for field in ("content_version", "content_sha256"):
            require(row[field] == expected[key][field], "Stale content version/hash in judgment")
        labels[key] = row["relevance"]
    require(set(labels) == set(expected), "Incomplete candidate coverage; unknown is not zero")
    return selected, labels


def compare_reviews(first, second, manifest, queries, qrels):
    selected, left = validate_review(first, manifest, queries, qrels)
    other_selected, right = validate_review(second, manifest, queries, qrels)
    require(normalized(first["reviewer"]) != normalized(second["reviewer"]), "Two different reviewers required")
    require(selected == other_selected, "Reviewers must judge the same queries independently")
    conflicts = [{"query_id": key[0], "content_id": key[1], "first": grade, "second": right[key]}
                 for key, grade in left.items() if grade != right[key]]
    count = len(left)
    agreement = (count - len(conflicts)) / count if count else None
    a, b = Counter(left.values()), Counter(right.values())
    chance = sum(a[grade] * b[grade] for grade in (0, 1, 2)) / (count * count) if count else None
    kappa = (agreement - chance) / (1 - chance) if chance is not None and chance < 1 else None
    return {"dataset_id": manifest["dataset_id"], "reviewed_queries": len(selected), "judgment_count": count,
            "exact_agreement": agreement, "cohen_kappa": kappa, "conflicts": conflicts,
            "status": "needs_adjudication" if conflicts else "agreed",
            "formal_test_ready": False,
            "qrels": [{**row, "relevance": left[(row["query_id"], row["content_id"])],
                       "label_status": "two_independent_reviews_agreed"}
                      for row in qrels if row["query_id"] in selected] if not conflicts else []}


def write_new_bundle(base, files):
    """Preflight every path before writing; never overwrite a review or prior version."""
    base = Path(base).resolve()
    for name in files:
        target = (base / name).resolve()
        require(target.is_relative_to(base) and not target.exists(), "Output exists or escapes bundle: " + name)
    base.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
