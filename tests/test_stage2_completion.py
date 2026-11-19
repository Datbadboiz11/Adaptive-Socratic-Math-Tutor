"""Revision and review lifecycle regressions. Synthetic reviews never write to content/."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/authoring"))
sys.path.insert(0, str(ROOT / "scripts/checks"))

from app.authoring_reviews import (
    CurriculumReview, LabelsReview, apply_curriculum_review, apply_labels_review,
)
from app.authoring_revisions import check_expanded_linear_answer, check_stage2_scope, check_text_encoding, distribution_shape
from app.content_authoring import digest
from app.curriculum import CurriculumRegistry
from app.oatutor_import import file_hash, read_json, registry_with_source
from app.retrieval_dev import build_dev_set
from prepare_oatutor_batch import (
    BATCH_ROOT, BATCH_ROOT_V2, DEV_PROPOSAL_V2, SELECTION_V2,
    check_batch, record_extended_review,
)
from check_stage2_completion import schema_artifacts


class Stage2CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = BATCH_ROOT_V2
        cls.created_at = datetime.fromisoformat(read_json(cls.batch / "manifest.json")["created_at"])
        cls.registry = CurriculumRegistry.model_validate(read_json(cls.batch / "registry-snapshot.json"))
        cls.selection = read_json(SELECTION_V2)
        cls.proposal = read_json(DEV_PROPOSAL_V2)
        cls.prepared = {cid: {name: read_json(cls.batch / cid / name) for name in
                             ("request.json", "draft.json", "checks.json", "review-template.json", "provenance.json")}
                        for cid in ("A02", "E02")}
        cls.dev = {name: read_json(cls.batch / "retrieval-dev" / name) for name in
                   ("corpus.json", "queries.json", "qrels.json", "manifest.json", "labels-review-template.json")}

    def identity(self):
        return {"review_id": "SYNTHETIC-TEST-ONLY", "reviewer": "Synthetic independent reviewer (unit tests only)",
                "reviewed_at": datetime.now(timezone.utc).isoformat(), "human_attestation": True,
                "decision": "approved", "comments": "Synthetic fixture only. Not a real content or label review."}

    @staticmethod
    def saved_file_hash(path):
        # Only review-output writes are mocked. Frozen-batch integrity reads remain real.
        return "0" * 64 if "SYNTHETIC-TEST-ONLY" in Path(path).parts else file_hash(path)

    def labels_payload(self):
        data = copy.deepcopy(self.dev["labels-review-template.json"])
        data.update(self.identity())
        for query in data["queries"]:
            query.update(checked=True, proposed_labels_accepted=True, comments="Synthetic test confirmation.")
        return data

    def curriculum_payload(self):
        data = read_json(self.batch / "curriculum-review-template.json")
        data.update(self.identity())
        for concept in data["concepts"]:
            concept.update(scope="pass", alignment="pass", comments="Synthetic test only, not a curriculum decision.")
        return data

    def apply_labels(self, payload):
        return apply_labels_review(self.dev["corpus.json"], self.dev["queries.json"], self.dev["qrels.json"],
                                   LabelsReview.model_validate(payload), {"Member 2"}, self.created_at)

    def test_both_frozen_batches_rebuild_without_mutation(self):
        self.assertEqual(check_batch(BATCH_ROOT)["problems"], 12)
        current = check_batch(self.batch)
        self.assertEqual((current["new_tasks_relative_to_v1"], current["reused_tasks_relative_to_v1"]), (2, 10))
        self.assertFalse(current["a07_complete_pack"])

    def test_a02_forward_scope_and_three_family_shapes(self):
        check_stage2_scope(self.prepared, self.registry)
        forms = next(c for c in self.registry.concepts if c.concept_id == "A02").supported_forms
        self.assertNotIn("Đặt nhân tử chung tuyến tính", forms)
        for record in self.prepared["A02"]["draft.json"]["problems"]:
            self.assertNotIn("nhân tử chung", record["prompt"].casefold())

    def test_a02_rejects_mathematically_equivalent_wrong_task_form(self):
        for expression in ("3*x+6", "x+x+6", "0*(x+2)"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                distribution_shape(expression)
        prepared = copy.deepcopy(self.prepared)
        prepared["A02"]["draft.json"]["problems"][0]["task"]["expression"] = "3*(x-2)"
        with self.assertRaisesRegex(ValueError, "declared family"):
            check_stage2_scope(prepared, self.registry)

    def test_a02_final_answer_must_be_expanded_and_collected(self):
        for answer in ("3*x+12", "-8*x+(-2)"):
            check_expanded_linear_answer(answer)
        for answer in ("3*(x+4)", "3*x+3*4", "x+2*x+12", "3*x+4+8"):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                check_expanded_linear_answer(answer)

    def test_scope_overlay_cannot_expand_a_concept(self):
        base = CurriculumRegistry.model_validate(read_json(self.batch / "registry-base.json"))
        selection = copy.deepcopy(self.selection)
        selection["scope_overrides"]["A02"]["supported_forms"].append("Geometry")
        with self.assertRaisesRegex(ValueError, "introduce new forms"):
            registry_with_source(base, selection, "2026-11-17")

    def test_a07_transfer_is_partial_and_retains_previous_ids_lineage_and_errors(self):
        fragment = read_json(self.batch / "A07-fragment.json")
        self.assertEqual((len(fragment["problems"]), len(fragment["examples"]), len(fragment["errors"]), len(fragment["query_drafts"])), (2, 1, 1, 4))
        self.assertFalse(fragment["complete_pack"])
        self.assertEqual(fragment["new_independent_problems"], 0)
        for problem in fragment["problems"]:
            self.assertEqual(problem["primary_skill_id"], "SK-A07-PRIMARY")
        self.assertTrue(all(p["previous_record_id"].startswith("D-A02-M2-OAT01-") for p in fragment["provenance"]))

    def test_old_partial_label_and_new_direct_label_have_separate_snapshots(self):
        old = read_json(BATCH_ROOT / "retrieval-dev/qrels.json")
        grades = lambda records: max(r["relevance"] for r in records if r["query_id"] == "DEV-E02-03")
        self.assertEqual(grades(old), 1)
        self.assertEqual(grades(self.dev["qrels.json"]), 2)
        self.assertEqual(self.dev["manifest.json"]["human_approved_labels"], 0)

    def test_utf8_loss_is_rejected_without_rejecting_a_real_question(self):
        check_text_encoding({"text": "Tính phân phối là gì?", "answers": ["Có thể giải thích không?"]})
        for text in ("T?nh ph?n ph?i", "Tiếng Việt \ufffd", "Bad\x00text"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "encoding"):
                check_text_encoding(text)

    def test_active_problem_indices_are_bounded(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["queries"][0]["active_problem_index"] = -1
        with self.assertRaisesRegex(ValueError, "problem index"):
            build_dev_set(proposal, self.prepared, self.registry, "TEST-ONLY")

    def test_query_paraphrases_can_share_an_intent_group(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["queries"][1]["intent_group"] = proposal["queries"][0]["intent_group"]
        result = build_dev_set(proposal, self.prepared, self.registry, "TEST-ONLY")
        self.assertEqual(result["manifest.json"]["query_count"], 24)

    def test_positive_relevance_is_not_required_just_because_candidates_are_eligible(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["queries"][0]["labels"] = {}
        result = build_dev_set(proposal, self.prepared, self.registry, "TEST-ONLY")
        self.assertTrue(result["queries.json"][0]["eligible_candidate_ids"])
        self.assertEqual(result["queries.json"][0]["proposed_relevant_ids"], [])

    def test_schema_exports_match_models(self):
        for path, content in schema_artifacts().items():
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_unfilled_templates_are_not_valid_review_signatures(self):
        with self.assertRaises(ValidationError):
            LabelsReview.model_validate(self.dev["labels-review-template.json"])
        with self.assertRaises(ValidationError):
            CurriculumReview.model_validate(read_json(self.batch / "curriculum-review-template.json"))

    def test_full_synthetic_label_review_creates_separate_candidate_only(self):
        original = digest(self.dev["qrels.json"])
        result = self.apply_labels(self.labels_payload())
        self.assertEqual(len(result["qrels.json"]), 192)
        self.assertTrue(all(r["label_status"] == "human_reviewed" for r in result["qrels.json"]))
        self.assertFalse(result["manifest.json"]["runtime_publication"])
        self.assertEqual(digest(self.dev["qrels.json"]), original)

    def test_stale_label_hashes_are_rejected(self):
        for field in ("corpus_sha256", "queries_sha256", "qrels_sha256"):
            payload = self.labels_payload()
            payload[field] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Stale"):
                self.apply_labels(payload)

    def test_self_review_is_rejected(self):
        payload = self.labels_payload()
        payload["reviewer"] = " member   2 "
        with self.assertRaisesRegex(ValueError, "independent"):
            self.apply_labels(payload)

    def test_future_and_predating_review_timestamps_are_rejected(self):
        for time in (datetime.now(timezone.utc) + timedelta(days=1), self.created_at - timedelta(seconds=1)):
            payload = self.labels_payload()
            payload["reviewed_at"] = time.isoformat()
            with self.subTest(time=time), self.assertRaisesRegex(ValueError, "timestamp"):
                self.apply_labels(payload)

    def test_approval_requires_all_queries_but_partial_changes_requested_can_be_recorded(self):
        payload = self.labels_payload()
        payload["queries"] = payload["queries"][:1]
        with self.assertRaisesRegex(ValueError, "every query"):
            self.apply_labels(payload)
        payload["decision"] = "changes_requested"
        self.assertIsNone(self.apply_labels(payload))

    def test_unchecked_and_duplicate_query_reviews_are_rejected(self):
        payload = self.labels_payload()
        payload["queries"][0]["checked"] = False
        with self.assertRaises(ValidationError):
            self.apply_labels(payload)
        payload = self.labels_payload()
        payload["queries"][-1] = copy.deepcopy(payload["queries"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.apply_labels(payload)

    def correction_payload(self, content_id, grade):
        payload = self.labels_payload()
        payload["queries"][0].update(proposed_labels_accepted=False, corrections=[{
            "content_id": content_id, "relevance": grade, "reason": "Synthetic correction for unit testing only."}])
        return payload

    def test_human_correction_to_zero_is_kept_and_no_positive_metric_case_is_reported(self):
        doc_id = self.dev["queries.json"][0]["proposed_relevant_ids"][0]
        result = self.apply_labels(self.correction_payload(doc_id, 0))
        self.assertEqual(result["queries.json"][0]["relevant_ids"], [])
        self.assertEqual(result["queries.json"][0]["proposed_relevant_ids"], [doc_id])
        self.assertEqual(result["queries.json"][0]["expected_relevance_result"], "no_relevant_content")
        self.assertEqual(result["queries.json"][0]["label_rationale"], "Synthetic test confirmation.")
        self.assertIn("DEV-A02-01", result["manifest.json"]["queries_without_direct_positive"])

    def test_forbidden_positive_and_unknown_correction_are_rejected(self):
        forbidden = next(r["content_id"] for r in self.dev["qrels.json"]
                         if r["query_id"] == "DEV-A02-01" and not r["authoring_eligible"])
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.apply_labels(self.correction_payload(forbidden, 2))
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.apply_labels(self.correction_payload("UNKNOWN-CONTENT", 1))

    def test_ambiguous_noop_and_duplicate_corrections_are_rejected(self):
        doc_id = self.dev["queries.json"][0]["proposed_relevant_ids"][0]
        with self.assertRaisesRegex(ValueError, "change the grade"):
            self.apply_labels(self.correction_payload(doc_id, 2))
        payload = self.correction_payload(doc_id, 1)
        payload["queries"][0]["proposed_labels_accepted"] = True
        with self.assertRaises(ValidationError):
            self.apply_labels(payload)
        payload = self.correction_payload(doc_id, 1)
        payload["queries"][0]["corrections"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate correction"):
            self.apply_labels(payload)

    def test_curriculum_approval_is_separate_from_pack_edges_and_a07(self):
        review = CurriculumReview.model_validate(self.curriculum_payload())
        result = apply_curriculum_review(self.registry, review, {"Member 2"}, self.created_at)
        self.assertEqual([c.review.status for c in result.concepts if c.concept_id in ("A02", "E02")], ["human_approved"] * 2)
        self.assertEqual(next(c for c in result.concepts if c.concept_id == "A07").review.status, "draft")
        self.assertTrue(all(e.review.status == "draft" for e in result.edges))
        self.assertEqual(self.prepared["A02"]["draft.json"]["review"]["status"], "draft")

    def test_stale_curriculum_hash_and_changed_grade_cannot_be_approved(self):
        for changes in ("hash", "grade", "source"):
            payload = self.curriculum_payload()
            if changes == "hash": payload["registry_sha256"] = "0" * 64
            if changes == "grade": payload["concepts"][0]["grade_levels"] = [12]
            if changes == "source": payload["concepts"][0]["source_id"] = "SRC-OATUTOR-PILOT-V1"
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                apply_curriculum_review(self.registry, CurriculumReview.model_validate(payload), {"Member 2"}, self.created_at)

    def test_curriculum_cannot_be_approved_with_unchecked_scope(self):
        payload = self.curriculum_payload()
        payload["concepts"][0]["scope"] = "not_checked"
        with self.assertRaises(ValidationError):
            CurriculumReview.model_validate(payload)
        payload["decision"] = "changes_requested"
        self.assertIsNone(apply_curriculum_review(self.registry, CurriculumReview.model_validate(payload), {"Member 2"}, self.created_at))

    def test_cli_label_review_records_receipt_without_modifying_frozen_files(self):
        review_path = ROOT / "artifacts/SYNTHETIC-NONEXISTENT-REVIEW.json"
        actual_read = read_json
        payload = self.labels_payload()
        def read(path):
            return payload if Path(path) == review_path else actual_read(path)
        with patch("prepare_oatutor_batch.read_json", side_effect=read), patch("prepare_oatutor_batch.write_json") as write, \
             patch("prepare_oatutor_batch.file_hash", side_effect=self.saved_file_hash), patch.object(Path, "mkdir"):
            result = record_extended_review(self.batch, review_path, "labels")
        self.assertTrue(result["approved_candidate"])
        self.assertFalse(result["runtime_publication"])
        self.assertEqual({call.args[0].name for call in write.call_args_list},
                         {"review.json", "queries.json", "qrels.json", "manifest.json", "receipt.json"})

    def test_cli_curriculum_review_records_only_candidate_registry(self):
        review_path = ROOT / "artifacts/SYNTHETIC-NONEXISTENT-REVIEW.json"
        actual_read = read_json
        payload = self.curriculum_payload()
        with patch("prepare_oatutor_batch.read_json", side_effect=lambda p: payload if Path(p) == review_path else actual_read(p)), \
             patch("prepare_oatutor_batch.write_json") as write, \
             patch("prepare_oatutor_batch.file_hash", side_effect=self.saved_file_hash), patch.object(Path, "mkdir"):
            result = record_extended_review(self.batch, review_path, "curriculum")
        self.assertTrue(result["approved_candidate"])
        self.assertEqual({call.args[0].name for call in write.call_args_list}, {"review.json", "registry-candidate.json", "receipt.json"})

    def test_cli_partial_changes_requested_produces_no_approved_label_candidate(self):
        review_path = ROOT / "artifacts/SYNTHETIC-NONEXISTENT-REVIEW.json"
        actual_read = read_json
        payload = self.labels_payload()
        payload.update(decision="changes_requested", queries=payload["queries"][:1])
        with patch("prepare_oatutor_batch.read_json", side_effect=lambda p: payload if Path(p) == review_path else actual_read(p)), \
             patch("prepare_oatutor_batch.write_json") as write, \
             patch("prepare_oatutor_batch.file_hash", side_effect=self.saved_file_hash), patch.object(Path, "mkdir"):
            result = record_extended_review(self.batch, review_path, "labels")
        self.assertFalse(result["approved_candidate"])
        self.assertEqual({call.args[0].name for call in write.call_args_list}, {"review.json", "receipt.json"})


if __name__ == "__main__":
    unittest.main()
