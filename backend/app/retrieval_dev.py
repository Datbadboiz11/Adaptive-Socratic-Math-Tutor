"""Pinned draft corpus and explicit proposed qrels, for authoring review only."""
from collections import Counter

from app.content_authoring import digest
from app.member2_contracts import RetrievalQuery
from app.oatutor_import import require


def candidate_corpus(prepared, registry, snapshot_id):
    documents = []
    for cid, files in sorted(prepared.items()):
        pack = files["draft.json"]
        concept = next(c for c in registry.concepts if c.concept_id == cid)
        for suffix, text, kind, level, disclosure in [
            ("explanation", pack["explanation"], "explanation", 0, "conceptual"),
            *[(f"hint-{h['level']}", h["text"], "hint", h["level"], h["disclosure"]) for h in pack["hints"]],
        ]:
            body = {"content_id": f"DEV-{cid}-{files['request.json']['revision']}-{suffix}",
                    "content_version": pack["content_version"], "concept_id": cid,
                    "skill_ids": [s.skill_id for s in concept.skills], "kind": kind, "text": text,
                    "hint_level": level, "disclosure": disclosure,
                    "grade_levels": concept.alignment.grade_levels, "source_group": None, "problem_id": None,
                    "pack_sha256": digest(pack), "review_status": "draft", "runtime_eligible": False}
            documents.append({**body, "content_sha256": digest(body)})
    return {"snapshot_id": snapshot_id, "usage": "authoring_dev_only_not_runtime", "documents": documents}


def blocking_reasons(document, query):
    reasons = []
    if document["concept_id"] != query["concept_id"] or query["target_skill_id"] not in document["skill_ids"]:
        reasons.append("concept_skill")
    if document["kind"] != query["purpose"]:
        reasons.append("purpose")
    if document["hint_level"] > query["allowed_hint_level"]:
        reasons.append("hint_level")
    if not set(document["grade_levels"]).intersection(query["grade_levels"]):
        reasons.append("grade")
    if document["problem_id"] is not None and document["problem_id"] == query["active_problem_id"]:
        reasons.append("active_problem")
    if document["source_group"] is not None and document["source_group"] in query["excluded_source_groups"]:
        reasons.append("source_group")
    return reasons


def build_dev_set(proposal, prepared, registry, snapshot_id):
    require(proposal["split"] == "dev" and proposal["human_review"] == {
        "status": "pending", "reviewer": None, "reviewed_at": None}, "Proposals cannot invent human review")
    corpus = candidate_corpus(prepared, registry, snapshot_id)
    corpus_sha = digest(corpus)
    queries, qrels = [], []
    seen_ids = set()
    require(20 <= len(proposal["queries"]) <= 30, "Need 20–30 dev queries")
    for spec in proposal["queries"]:
        cid = spec["concept_id"]
        pack = prepared[cid]["draft.json"]
        concept = next(c for c in registry.concepts if c.concept_id == cid)
        require(type(spec["active_problem_index"]) is int and 0 <= spec["active_problem_index"] < len(pack["problems"]),
                "Invalid active problem index")
        problem = pack["problems"][spec["active_problem_index"]]
        require(spec["query_id"] not in seen_ids and bool(spec["intent_group"].strip()),
                "Duplicate query ID or missing intent group")
        seen_ids.add(spec["query_id"])
        validated = RetrievalQuery(query=spec["text"], concept_id=cid,
                                   target_skill_id=problem["primary_skill_id"], purpose=spec["purpose"], top_k=3)
        require(type(spec["allowed_hint_level"]) is int and 0 <= spec["allowed_hint_level"] <= 3,
                "Invalid hint permission")
        query = {"query_id": spec["query_id"], **validated.model_dump(mode="json"),
                 "allowed_hint_level": spec["allowed_hint_level"], "grade_levels": concept.alignment.grade_levels,
                 "active_problem_id": problem["case_id"], "excluded_source_groups": [problem["source_group"]],
                 "intent_group": spec["intent_group"], "split": "dev", "snapshot_id": snapshot_id,
                 "corpus_sha256": corpus_sha, "label_status": "ai_proposed_pending_human_review",
                 "label_rationale": spec["rationale"], "expected_runtime": "no_eligible_content_drafts_only"}
        require(set(spec["labels"]).issubset({"explanation", "hint-1", "hint-2", "hint-3"}), "Unknown document label")
        for value in spec["labels"].values():
            require(type(value) is int and value in (0, 1, 2), "Invalid relevance grade")
        eligible_ids, positive_ids = [], []
        for document in corpus["documents"]:
            reasons = blocking_reasons(document, query)
            suffix = "explanation" if document["kind"] == "explanation" else f"hint-{document['hint_level']}"
            grade = spec["labels"].get(suffix, 0) if document["concept_id"] == cid else 0
            require(not reasons or grade == 0, "Positive relevance on a forbidden candidate")
            if not reasons:
                eligible_ids.append(document["content_id"])
            if grade > 0:
                positive_ids.append(document["content_id"])
            qrels.append({"query_id": query["query_id"], "content_id": document["content_id"],
                          "content_version": document["content_version"], "content_sha256": document["content_sha256"],
                          "relevance": grade, "authoring_eligible": not reasons, "blocking_reasons": reasons,
                          "label_status": "ai_proposed_pending_human_review"})
        require(eligible_ids or not positive_ids, "Forbidden candidates cannot have positive judgments")
        query.update(eligible_candidate_ids=eligible_ids, proposed_relevant_ids=positive_ids,
                     expected_authoring_result="candidates" if eligible_ids else "no_eligible_content")
        queries.append(query)
    counts = Counter(q["concept_id"] for q in queries)
    require(counts == {"A02": 12, "E02": 12}, "Expected twelve queries per pilot concept")
    split_groups = sorted({p["split_group"] for f in prepared.values() for p in f["provenance.json"]})
    manifest = {"snapshot_id": snapshot_id, "corpus_sha256": corpus_sha, "queries_sha256": digest(queries),
                "qrels_sha256": digest(qrels), "split": "dev", "query_count": len(queries),
                "candidate_count": len(corpus["documents"]), "judgment_count": len(qrels),
                "fallback_count": sum(q["expected_authoring_result"] == "no_eligible_content" for q in queries),
                "source_and_lineage_groups_reserved_for_dev": split_groups,
                "test_reuse": "Do not move these problems, their lesson groups, variants or query paraphrases into final test",
                "human_review": proposal["human_review"], "evaluation_status": "not_run",
                "metric_note": "Small draft corpus for plumbing and relevance review; no retrieval performance claim. "
                               "Recall/Hit use relevance >= 2; graded nDCG gains 0,1,3. No-positive queries: N/A, evaluate fallback separately.",
                "runtime_eligible_documents": 0, "human_approved_labels": 0}
    review = {"snapshot_id": snapshot_id, "corpus_sha256": corpus_sha,
              "queries_sha256": digest(queries), "qrels_sha256": digest(qrels),
              "reviewer": None, "reviewed_at": None, "decision": "pending",
              "instructions": "Người thật đối chiếu từng query với toàn bộ ứng viên; ghi sửa nhãn nếu cần. "
                              "Mẫu này không tự phê duyệt nhãn hoặc nội dung.",
              "queries": [{"query_id": q["query_id"], "checked": False,
                           "proposed_labels_accepted": None, "corrections": [], "comments": ""} for q in queries]}
    return {"corpus.json": corpus, "queries.json": queries, "qrels.json": qrels,
            "manifest.json": manifest, "labels-review-template.json": review}
