"""Explicit independent review of curriculum scopes and dev labels; no publication."""
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.content_authoring import digest
from app.contracts import Contract, Identifier
from app.curriculum import CurriculumRegistry, Text
from app.oatutor_import import require

SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Grade = Annotated[int, Field(strict=True, ge=0, le=2)]


class IndependentReview(Contract):
    review_id: Identifier
    reviewer: Annotated[str, Field(min_length=1, max_length=160)]
    reviewed_at: AwareDatetime
    human_attestation: Literal[True]
    decision: Literal["approved", "changes_requested"]
    comments: Text


def check_identity(review, authors, created_at):
    normalize = lambda value: " ".join(value.split()).casefold()
    require(normalize(review.reviewer) not in {normalize(a) for a in authors}, "An independent reviewer is required")
    require(created_at <= review.reviewed_at <= datetime.now(timezone.utc), "Review timestamp is outside the batch lifetime")


class LabelCorrection(Contract):
    content_id: Identifier
    relevance: Grade
    reason: Text


class QueryLabelReview(Contract):
    query_id: Identifier
    checked: Literal[True]
    proposed_labels_accepted: Annotated[bool, Field(strict=True)]
    corrections: list[LabelCorrection]
    comments: Text

    @model_validator(mode="after")
    def explicit_acceptance_or_corrections(self):
        if self.proposed_labels_accepted == bool(self.corrections):
            raise ValueError("Accept the proposed labels or supply corrections, not both")
        return self


class LabelsReview(IndependentReview):
    protocol_version: Literal["labels-review-1.0.0"] = "labels-review-1.0.0"
    snapshot_id: Identifier
    corpus_sha256: SHA256
    queries_sha256: SHA256
    qrels_sha256: SHA256
    queries: list[QueryLabelReview] = Field(min_length=1, max_length=30)


def label_review_template(dev):
    manifest = dev["manifest.json"]
    return {"protocol_version": "labels-review-1.0.0", "review_id": "FILL-UNIQUE-REVIEW-ID",
            "reviewer": None, "reviewed_at": None, "human_attestation": False, "decision": "changes_requested",
            "comments": "Người review thật kiểm tra đủ ứng viên của từng query; ghi xác nhận hoặc chỉnh nhãn.",
            **{key: manifest[key] for key in ("snapshot_id", "corpus_sha256", "queries_sha256", "qrels_sha256")},
            "queries": [{"query_id": q["query_id"], "checked": False, "proposed_labels_accepted": None,
                         "corrections": [], "comments": ""} for q in dev["queries.json"]]}


def apply_labels_review(corpus, queries, qrels, review, authors, created_at):
    check_identity(review, authors, created_at)
    require(review.snapshot_id == corpus["snapshot_id"] and review.corpus_sha256 == digest(corpus)
            and review.queries_sha256 == digest(queries) and review.qrels_sha256 == digest(qrels), "Stale label review hashes")
    ids = [q.query_id for q in review.queries]
    known_ids = {q["query_id"] for q in queries}
    require(len(ids) == len(set(ids)) and set(ids).issubset(known_ids), "Unknown or duplicate reviewed query")
    if review.decision == "approved":
        require(set(ids) == known_ids, "Review every query exactly once before approval")
    judgments = {(r["query_id"], r["content_id"]): dict(r) for r in qrels}
    require(len(judgments) == len(qrels) == len(queries) * len(corpus["documents"]), "Incomplete judgment matrix")
    expected_keys = {(q["query_id"], d["content_id"]) for q in queries for d in corpus["documents"]}
    require(set(judgments) == expected_keys, "Judgments do not match the pinned query/corpus matrix")
    for query_review in review.queries:
        corrected = set()
        for correction in query_review.corrections:
            key = query_review.query_id, correction.content_id
            require(key in judgments and key not in corrected, "Unknown or duplicate correction")
            corrected.add(key)
            judgment = judgments[key]
            require(correction.relevance != judgment["relevance"], "Correction must change the grade")
            require(judgment["authoring_eligible"] or correction.relevance == 0, "Positive label on forbidden content")
            judgment.update(relevance=correction.relevance, human_correction_reason=correction.reason)
    if review.decision != "approved":
        return None
    reviewed_qrels = []
    for original in qrels:
        item = judgments[original["query_id"], original["content_id"]]
        item.update(label_status="human_reviewed", review_id=review.review_id)
        reviewed_qrels.append(item)
    reviewed_queries = []
    review_by_id = {q.query_id: q for q in review.queries}
    for query in queries:
        relevant = [r["content_id"] for r in reviewed_qrels if r["query_id"] == query["query_id"] and r["relevance"] > 0]
        reviewed_queries.append({**query, "label_status": "human_reviewed", "review_id": review.review_id,
                                 "relevant_ids": relevant,
                                 "original_proposal_rationale": query["label_rationale"],
                                 "label_rationale": review_by_id[query["query_id"]].comments,
                                 "expected_relevance_result": "has_relevant_content" if relevant else "no_relevant_content"})
    no_direct_positive = [q["query_id"] for q in queries if not any(
        r["query_id"] == q["query_id"] and r["relevance"] >= 2 for r in reviewed_qrels)]
    return {"qrels.json": reviewed_qrels, "queries.json": reviewed_queries, "manifest.json": {
        "snapshot_id": corpus["snapshot_id"], "corpus_sha256": digest(corpus),
        "queries_sha256": digest(reviewed_queries), "qrels_sha256": digest(reviewed_qrels),
        "source_queries_sha256": digest(queries), "source_qrels_sha256": digest(qrels),
        "review_sha256": digest(review.model_dump(mode="json")), "human_review": {
            "reviewer": review.reviewer, "reviewed_at": review.reviewed_at.isoformat(), "review_id": review.review_id},
        "relevance_threshold": 2, "queries_without_direct_positive": no_direct_positive,
        "runtime_publication": False, "content_review_is_separate": True,
    }}


class ConceptScopeReview(Contract):
    concept_id: Identifier
    scope: Literal["pass", "fail", "not_checked"]
    alignment: Literal["pass", "fail", "not_checked"]
    source_id: Identifier
    locator: Text
    grade_levels: list[Annotated[int, Field(strict=True, ge=6, le=12)]] = Field(min_length=1)
    comments: Text


class CurriculumReview(IndependentReview):
    protocol_version: Literal["curriculum-review-1.0.0"] = "curriculum-review-1.0.0"
    registry_sha256: SHA256
    concepts: list[ConceptScopeReview] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def complete_approval(self):
        if self.decision == "approved" and any(c.scope != "pass" or c.alignment != "pass" for c in self.concepts):
            raise ValueError("Curriculum approval requires scope and alignment checks to pass")
        return self


def curriculum_review_template(registry):
    return {"protocol_version": "curriculum-review-1.0.0", "review_id": "FILL-UNIQUE-REVIEW-ID",
            "reviewer": None, "reviewed_at": None, "human_attestation": False, "decision": "changes_requested",
            "comments": "Đối chiếu chương trình Việt Nam; ghi rõ mục/trang đã thực sự kiểm tra.",
            "registry_sha256": digest(registry.model_dump(mode="json")),
            "concepts": [{"concept_id": c.concept_id, "scope": "not_checked", "alignment": "not_checked",
                          "source_id": c.alignment.source_id, "grade_levels": c.alignment.grade_levels,
                          "locator": c.alignment.locator, "comments": ""}
                         for c in registry.concepts if c.concept_id in ("A02", "E02")]}


def apply_curriculum_review(registry, review, authors, created_at):
    check_identity(review, authors, created_at)
    require(review.registry_sha256 == digest(registry.model_dump(mode="json")), "Stale curriculum review hash")
    ids = [c.concept_id for c in review.concepts]
    require(len(ids) == len(set(ids)) and set(ids) == {"A02", "E02"}, "Review A02/E02 exactly once")
    mapping = {c.concept_id: c for c in registry.concepts}
    for item in review.concepts:
        concept = mapping[item.concept_id]
        require(item.source_id == concept.alignment.source_id, "Curriculum source mismatch")
        require(len(item.grade_levels) == len(set(item.grade_levels)), "Duplicate grade")
        if review.decision == "approved":
            require(set(item.grade_levels) == set(concept.alignment.grade_levels), "Grade change needs a new draft revision")
    if review.decision != "approved":
        return None
    data = registry.model_dump(mode="json")
    for concept in data["concepts"]:
        if concept["concept_id"] in ids:
            item = next(c for c in review.concepts if c.concept_id == concept["concept_id"])
            concept["alignment"].update(status="human_approved", reviewer=review.reviewer, locator=item.locator)
            concept["review"].update(status="human_approved", human_reviewer=review.reviewer,
                                     reviewed_at=review.reviewed_at.isoformat())
    return CurriculumRegistry.model_validate(data)
