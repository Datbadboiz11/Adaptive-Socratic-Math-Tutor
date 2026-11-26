"""OATutor import boundaries, exact math and proposed dev labels; no network or file writes."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/authoring"))

from app.content_authoring import digest
from app.curriculum import load_curriculum
from app.oatutor_import import (
    file_hash, item_paths, normalize_math, prepare_packs, read_json, selection_paths,
    source_item, verify_snapshot,
)
from app.retrieval_dev import blocking_reasons, build_dev_set
from prepare_oatutor_batch import (
    BATCH_ROOT, DEV_PROPOSAL, SELECTION, SNAPSHOT_ID, SOURCE_ROOT, check_batch,
)


class OATutorPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selection = read_json(SELECTION)
        cls.proposal = read_json(DEV_PROPOSAL)
        cls.registry, cls.bank = load_curriculum()
        cls.configs = {cid: read_json(ROOT / "content/authoring/configs" / (cid.lower() + ".v1.json"))
                       for cid in ("A02", "E02")}
        cls.staged, cls.prepared = cls.prepare(cls.selection)
        cls.dev = build_dev_set(cls.proposal, cls.prepared, cls.staged, SNAPSHOT_ID)

    @classmethod
    def prepare(cls, selection):
        return prepare_packs(selection, SOURCE_ROOT, cls.registry, cls.bank, cls.configs)

    def source_spec(self, index=2):
        return {**copy.deepcopy(self.selection["concepts"][0]["problems"][index]),
                "commit": self.selection["upstream_commit"]}

    def changed_raw(self, spec, mutate):
        paths = item_paths(spec["upstream_problem_id"], spec["upstream_steps"])
        raw = {str(SOURCE_ROOT / p): read_json(SOURCE_ROOT / p) for p in paths}
        mutate(raw, paths)
        return patch("app.oatutor_import.read_json", side_effect=lambda p: copy.deepcopy(raw[str(p)]))

    def test_source_pin_and_exact_selected_files(self):
        manifest = verify_snapshot(self.selection, SOURCE_ROOT)
        self.assertEqual(len(manifest["files"]), 29)
        self.assertEqual(sorted(f["path"] for f in manifest["files"]), selection_paths(self.selection))

    def test_source_tamper_is_detected_offline(self):
        original = file_hash
        with patch("app.oatutor_import.file_hash", side_effect=lambda p: "0" * 64 if Path(p).name == "README.md" else original(p)):
            with self.assertRaisesRegex(ValueError, "Changed upstream file"):
                verify_snapshot(self.selection, SOURCE_ROOT)

    def test_normalizes_declared_small_tex_subset(self):
        self.assertEqual(normalize_math(r"Simplify $$\left(-2\right) \left(4y+1\right)$$.", "y"), "(-2)*(4*x+1)")
        self.assertEqual(normalize_math("$$12x+8=6x+2$$"), "12*x+8=6*x+2")

    def test_rejects_unsupported_tex_prose_code_and_ambiguous_spans(self):
        for value in [r"$$\frac{1}{2}x$$", "Simplify 3x", "__import__('os')", "$$x$$ plus $$1$$", "$$x**100$$!"]:
            with self.subTest(value=value):
                # Unsupported power syntax is rejected by the bounded math checker,
                # while unknown markup/prose must fail at the adapter boundary.
                if "**" in value:
                    from app.authoring_math import polynomial
                    with self.assertRaises(ValueError):
                        polynomial(normalize_math(value))
                else:
                    with self.assertRaises(ValueError):
                        normalize_math(value)

    def test_joined_negative_answers_match_original_coefficient_and_constant(self):
        expression, answer, provenance = source_item(self.source_spec(), SOURCE_ROOT)
        self.assertEqual(expression, "(-2)*(4*x+1)")
        self.assertEqual(answer, "-8*x+(-2)")
        self.assertEqual(len(provenance["upstream_step_ids"]), 2)
        self.assertTrue(any(n["license"] == "" for n in provenance["upstream_license_fields"]))

    def test_wrong_component_answer_is_rejected(self):
        spec = self.source_spec()
        with self.changed_raw(spec, lambda raw, paths: raw[str(SOURCE_ROOT / paths[1])].update(stepAnswer=["$$8$$"])):
            with self.assertRaisesRegex(ValueError, "component answers disagree"):
                source_item(spec, SOURCE_ROOT)

    def test_source_license_conflict_is_not_silently_overridden(self):
        spec = self.source_spec()
        with self.changed_raw(spec, lambda raw, paths: raw[str(SOURCE_ROOT / paths[0])].update(license="All rights reserved")):
            with self.assertRaisesRegex(ValueError, "license needs review"):
                source_item(spec, SOURCE_ROOT)

    def test_changed_identity_and_variabilization_are_rejected(self):
        spec = self.source_spec()
        for changes in ({"id": "different"}, {"variabilization": {"x": [1, 2]}}):
            with self.subTest(changes=changes), self.changed_raw(spec, lambda raw, paths: raw[str(SOURCE_ROOT / paths[0])].update(changes)):
                with self.assertRaises(ValueError):
                    source_item(spec, SOURCE_ROOT)

    def test_whole_lesson_lineage_cannot_be_split_by_family(self):
        spec = self.source_spec()
        spec["split_group"] = "positive-only"
        with self.assertRaisesRegex(ValueError, "whole source lesson"):
            source_item(spec, SOURCE_ROOT)

    def test_adapter_rejects_path_traversal_and_floating_commit(self):
        with self.assertRaises(ValueError):
            item_paths("../../other", ["a"])
        selection = copy.deepcopy(self.selection)
        selection["upstream_commit"] = "main"
        with self.assertRaisesRegex(ValueError, "full commit"):
            selection_paths(selection)

    def test_preparation_preserves_canonical_inputs_and_distinguishes_origins(self):
        before = digest(self.registry.model_dump(mode="json")), digest(self.bank.model_dump(mode="json"))
        _, packs = self.prepare(self.selection)
        origins = [r for f in packs.values() for r in f["provenance.json"] if r["record_type"] == "problem"]
        self.assertEqual(sum(p["origin_kind"] == "oatutor_adapted" for p in origins), 8)
        self.assertEqual(sum(p["origin_kind"] == "ai_generated_supplement" for p in origins), 4)
        self.assertEqual(before, (digest(self.registry.model_dump(mode="json")), digest(self.bank.model_dump(mode="json"))))
        for files in packs.values():
            self.assertTrue(files["checks.json"]["passed"])
            self.assertEqual(files["draft.json"]["review"]["status"], "draft")
            self.assertIsNone(files["review-template.json"]["reviewer"])

    def test_incorrect_synthetic_reference_is_rejected(self):
        selection = copy.deepcopy(self.selection)
        selection["concepts"][1]["problems"][2]["answer"] = "8"
        with self.assertRaisesRegex(ValueError, "Wrong reference answer"):
            self.prepare(selection)

    def test_dev_set_has_complete_proposed_labels_and_four_fallbacks(self):
        manifest = self.dev["manifest.json"]
        self.assertEqual((manifest["query_count"], manifest["candidate_count"], manifest["judgment_count"]), (24, 8, 192))
        self.assertEqual(manifest["fallback_count"], 4)
        self.assertEqual(manifest["human_approved_labels"], 0)
        self.assertEqual(manifest["runtime_eligible_documents"], 0)
        self.assertEqual(manifest["evaluation_status"], "not_run")
        self.assertTrue(all(r["label_status"] == "ai_proposed_pending_human_review" for r in self.dev["qrels.json"]))

    def test_positive_labels_cannot_bypass_hint_permission(self):
        proposal = copy.deepcopy(self.proposal)
        proposal["queries"][10]["labels"] = {"hint-1": 2}
        with self.assertRaisesRegex(ValueError, "forbidden candidate"):
            build_dev_set(proposal, self.prepared, self.staged, SNAPSHOT_ID)

    def test_candidate_corpus_has_no_private_answers_steps_or_upstream_terminal_hints(self):
        corpus = self.dev["corpus.json"]
        self.assertEqual(corpus["usage"], "authoring_dev_only_not_runtime")
        forbidden = {"reference_answer", "reference_steps", "hintAnswer", "stepAnswer", "errors", "problems"}
        for doc in corpus["documents"]:
            self.assertFalse(forbidden.intersection(doc))
            self.assertEqual(doc["review_status"], "draft")
            self.assertIs(doc["runtime_eligible"], False)

    def test_filter_checks_grade_active_problem_and_source_group(self):
        doc = copy.deepcopy(self.dev["corpus.json"]["documents"][0])
        query = copy.deepcopy(self.dev["queries.json"][0])
        doc.update(problem_id=query["active_problem_id"], source_group=query["excluded_source_groups"][0], grade_levels=[12])
        self.assertTrue({"grade", "active_problem", "source_group"}.issubset(blocking_reasons(doc, query)))

    def test_partial_relevance_is_not_inflated_into_direct_support(self):
        query_id = "DEV-E02-03"
        grades = [r["relevance"] for r in self.dev["qrels.json"] if r["query_id"] == query_id]
        self.assertEqual(max(grades), 1)

    def test_immutable_batch_rebuild_and_publication_boundary(self):
        summary = check_batch(BATCH_ROOT)
        self.assertEqual(summary["status"], "ready_for_review_not_approved")
        self.assertFalse(summary["runtime_publication"])


if __name__ == "__main__":
    unittest.main()
