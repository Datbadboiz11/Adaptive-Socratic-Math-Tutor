"""Authoring correctness, provider isolation and review lifecycle; no paid calls or deletion."""
import copy
from datetime import datetime, timedelta, timezone
import json
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/checks"))

from app.authoring_runs import (
    GenerationError, RunStore, TEMPLATE, create_run, generate_openai, load_json, pilot_replay, review_run, verify_run,
)
from app.authoring_math import scalar
from app.content_authoring import (
    ContentReview, DraftRequest, GeneratedContent, apply_review, build_prompt,
    check_draft, digest, make_draft, request_concept, review_template,
)
from app.curriculum import ConceptPack, PilotBank, load_curriculum, safe_chunks
from check_authoring import artifacts, audit


class AuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.bank = load_curriculum()

    def setUp(self):
        self.request = DraftRequest.model_validate(load_json(ROOT / "content/authoring/configs/a02.v1.json"))
        self.content, _ = pilot_replay(self.request, self.bank)
        self.pack = make_draft(self.content, self.request)

    def changed_pack(self, mutate):
        data = self.pack.model_dump(mode="json")
        mutate(data)
        return ConceptPack.model_validate(data)

    def codes(self, pack):
        return {i.code for i in check_draft(pack, self.request, self.registry, self.bank).issues if i.severity == "error"}

    def review(self, **changes):
        values = {"review_id": "synthetic-review", "reviewer": "Synthetic independent reviewer",
                  "reviewed_at": datetime.now(timezone.utc), "pack_sha256": digest(self.pack.model_dump(mode="json")),
                  "decision": "approved", "checklist": {k: "pass" for k in review_template(self.pack)["checklist"]},
                  "comments": "Synthetic unit test, not actual curriculum review."}
        values.update(changes)
        return ContentReview.model_validate(values)

    def test_two_configured_replays_pass_math_and_keep_drafts_unpublished(self):
        self.assertEqual([x["concept_id"] for x in audit("legacy")], ["A02", "E02"])
        self.assertEqual(self.pack.review.status, "draft")
        self.assertIsNone(self.pack.review.human_reviewer)
        self.assertTrue(check_draft(self.pack, self.request, self.registry, self.bank).passed)

    def test_prompt_contains_scope_versions_families_sources_and_budget(self):
        prompt = build_prompt(self.request, self.registry, TEMPLATE.read_text(encoding="utf-8"))
        context = json.loads(prompt[1]["content"])
        self.assertEqual(context["concept"]["concept_id"], "A02")
        self.assertEqual(context["id_prefix"], self.request.id_prefix)
        self.assertEqual(len(context["request"]["families"]), 3)
        self.assertIn("excluded_forms", context["concept"])
        self.assertEqual(context["request"]["max_output_tokens"], 8000)

    def test_model_cannot_supply_review_or_version_metadata(self):
        for field, value in (("review", {"status": "human_approved"}), ("content_version", "fake")):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                GeneratedContent.model_validate({**self.content.model_dump(mode="json"), field: value})

    def test_missing_authoring_scope_or_unknown_source_is_rejected_before_generation(self):
        for change in ({"concept_id": "A09"}, {"source_ids": ["missing"]}, {"content_version": "wrong"}):
            request = DraftRequest.model_validate({**self.request.model_dump(mode="json"), **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                request_concept(request, self.registry)

    def test_wrong_answer_step_and_unsupported_task_have_locations(self):
        pack = self.changed_pack(lambda d: d["problems"][0].update(reference_answer="3*x+999"))
        result = check_draft(pack, self.request, self.registry, self.bank)
        self.assertTrue(any(i.code == "invalid_math" and i.path == "problems[0]" for i in result.issues))
        pack = self.changed_pack(lambda d: d["problems"][0]["reference_steps"].append("3*x+999"))
        self.assertIn("invalid_math", self.codes(pack))
        pack = self.changed_pack(lambda d: d["problems"][0]["task"].update(kind="numeric"))
        self.assertIn("unsupported_task", self.codes(pack))

    def test_cross_record_id_collision_and_existing_ids_are_rejected(self):
        for mutation in (lambda d: d["examples"][0].update(case_id=d["problems"][0]["case_id"]),
                         lambda d: d["examples"][0].update(case_id="EX-A02-01")):
            self.assertIn("invalid_record_id", self.codes(self.changed_pack(mutation)))

    def concept_request(self, concept_id):
        pack = next(p for p in self.bank.packs if p.concept_id == concept_id)
        families = {p.family_id: p.source_group for p in pack.problems}
        return DraftRequest.model_validate({**self.request.model_dump(mode="json"), "concept_id": concept_id,
            "families": [{"family_id": f, "source_group": g, "description": "Synthetic test family"} for f, g in families.items()]})

    def test_n04_requires_reduced_form_not_only_equal_value(self):
        request = self.concept_request("N04")
        content, _ = pilot_replay(request, self.bank)
        pack = make_draft(content, request)
        value = scalar(pack.problems[0].reference_answer)
        data = pack.model_dump(mode="json")
        data["problems"][0]["reference_answer"] = f"{value.numerator*2}/{value.denominator*2}"
        result = check_draft(ConceptPack.model_validate(data), request, self.registry, self.bank)
        self.assertTrue(any(i.code == "fraction_not_reduced" for i in result.issues))

    def test_f05_reports_coverage_limit_instead_of_claiming_axis_checker(self):
        request = self.concept_request("F05")
        content, _ = pilot_replay(request, self.bank)
        result = check_draft(make_draft(content, request), request, self.registry, self.bank)
        self.assertTrue(any(i.code == "partial_concept_scope" and i.severity == "warning" for i in result.issues))

    def test_family_source_group_and_skill_must_match_declared_scope(self):
        for field, value, code in (("source_group", "NEW-GROUP", "source_group"),
                                   ("primary_skill_id", "SK-N01-SIGNED-ADD", "unknown_skill")):
            pack = self.changed_pack(lambda d: d["problems"][0].update({field: value}))
            self.assertIn(code, self.codes(pack))
        pack = self.changed_pack(lambda d: d["problems"][0].update(family_id=d["problems"][2]["family_id"]))
        self.assertIn("family_coverage", self.codes(pack))

    def test_exact_task_duplicates_and_examples_copying_current_task_are_rejected(self):
        pack = self.changed_pack(lambda d: d["problems"][1].update(task=d["problems"][0]["task"]))
        self.assertIn("duplicate_task", self.codes(pack))
        pack = self.changed_pack(lambda d: d["examples"][0].update(task=d["problems"][0]["task"]))
        self.assertIn("example_reuses_problem", self.codes(pack))

    def test_wrong_first_error_and_unsafe_later_step_are_detected(self):
        pack = self.changed_pack(lambda d: d["errors"][0].update(response_steps=["3*x+3*2", "3*x+2"], first_error_step=1))
        self.assertIn("wrong_error_label", self.codes(pack))
        pack = self.changed_pack(lambda d: d["errors"][0]["response_steps"].append("__import__('os')"))
        self.assertIn("invalid_error_trace", self.codes(pack))

    def test_final_answer_in_polynomial_or_equation_hint_is_rejected(self):
        pack = self.changed_pack(lambda d: d["hints"][0].update(text="Đáp án là " + d["problems"][0]["reference_answer"]))
        self.assertIn("answer_disclosure", self.codes(pack))
        request = DraftRequest.model_validate(load_json(ROOT / "content/authoring/configs/e02.v1.json"))
        content, _ = pilot_replay(request, self.bank)
        pack = make_draft(content, request)
        data = pack.model_dump(mode="json")
        data["hints"][0]["text"] = "Đáp án là x = " + data["problems"][0]["reference_answer"]
        result = check_draft(ConceptPack.model_validate(data), request, self.registry, self.bank)
        self.assertTrue(any(i.code == "answer_disclosure" for i in result.issues))

    def test_machine_pass_does_not_fill_manual_review_template(self):
        template = review_template(self.pack)
        self.assertIsNone(template["reviewer"])
        self.assertTrue(all(v == "not_checked" for v in template["checklist"].values()))
        with self.assertRaises(ValidationError):
            ContentReview.model_validate(template)

    def test_approval_requires_all_dimensions_and_independent_reviewer(self):
        with self.assertRaises(ValidationError):
            self.review(checklist={**self.review().checklist.model_dump(), "disclosure": "not_checked"})
        with self.assertRaises(ValueError):
            apply_review(self.pack, self.review(reviewer="  MEMBER   2 "), self.request, self.registry, self.bank)

    def test_review_is_bound_to_exact_hash_and_future_signatures_are_rejected(self):
        for review in (self.review(pack_sha256="0" * 64),
                       self.review(reviewed_at=datetime.now(timezone.utc) + timedelta(days=1))):
            with self.assertRaises(ValueError):
                apply_review(self.pack, review, self.request, self.registry, self.bank)

    def test_math_fail_cannot_be_approved_and_changes_requested_never_publishes(self):
        pack = self.changed_pack(lambda d: d["problems"][0].update(reference_answer="999"))
        review = self.review(pack_sha256=digest(pack.model_dump(mode="json")))
        with self.assertRaises(ValueError):
            apply_review(pack, review, self.request, self.registry, self.bank)
        self.assertIsNone(apply_review(self.pack, self.review(decision="changes_requested"), self.request, self.registry, self.bank))

    def test_synthetic_pack_approval_does_not_approve_concept_or_alignment(self):
        approved = apply_review(self.pack, self.review(), self.request, self.registry, self.bank)
        self.assertEqual(approved.review.status, "human_approved")
        bank = PilotBank.model_validate({**self.bank.model_dump(mode="json"), "packs": [
            approved.model_dump(mode="json") if p.concept_id == "A02" else p.model_dump(mode="json") for p in self.bank.packs]})
        self.assertEqual(safe_chunks(self.registry, bank, "A02"), [])
        self.assertEqual(self.pack.review.status, "draft")

    def test_openai_adapter_uses_bounded_structured_output_without_retries(self):
        factory = MagicMock()
        client = factory.return_value.__enter__.return_value
        client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=self.content,
            model="synthetic-model", id="synthetic-response", usage=SimpleNamespace(model_dump=lambda: {"output_tokens": 123}))
        with patch.dict(os.environ, {"AUTHORING_LLM_ENABLED": "true", "OPENAI_API_KEY": "synthetic-key"}):
            content, metadata = generate_openai(self.request, [{"role": "system", "content": "synthetic prompt"}], factory)
        self.assertEqual(content, self.content)
        self.assertEqual(metadata["model_calls"], 1)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        self.assertEqual(factory.call_args.kwargs["timeout"], 45)
        self.assertFalse(client.responses.parse.call_args.kwargs["store"])
        self.assertIs(client.responses.parse.call_args.kwargs["text_format"], GeneratedContent)
        self.assertEqual(client.responses.parse.call_args.kwargs["max_output_tokens"], 8000)

    def test_provider_failures_do_not_expose_secrets_or_call_again(self):
        factory = MagicMock()
        client = factory.return_value.__enter__.return_value
        client.responses.parse.side_effect = RuntimeError("synthetic-secret-key must not leak")
        with patch.dict(os.environ, {"AUTHORING_LLM_ENABLED": "true", "OPENAI_API_KEY": "synthetic-secret-key"}):
            with self.assertRaises(GenerationError) as caught:
                generate_openai(self.request, [], factory)
        self.assertNotIn("synthetic-secret-key", str(caught.exception))
        self.assertEqual(client.responses.parse.call_count, 1)
        with patch.dict(os.environ, {"AUTHORING_LLM_ENABLED": "false"}):
            factory.reset_mock()
            with self.assertRaises(GenerationError):
                generate_openai(self.request, [], factory)
            factory.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("openai") and importlib.util.find_spec("httpx"), "Optional SDK transport test requires installed OpenAI/httpx")
    def test_real_sdk_parses_structured_output_with_mock_http_transport(self):
        import httpx
        from openai import OpenAI
        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            return httpx.Response(200, json={
                "id": "synthetic-response", "object": "response", "created_at": 0,
                "status": "completed", "model": "synthetic-model",
                "output": [{"id": "synthetic-message", "type": "message", "status": "completed", "role": "assistant",
                    "content": [{"type": "output_text", "text": self.content.model_dump_json(), "annotations": []}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            })

        def factory(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        with patch.dict(os.environ, {"AUTHORING_LLM_ENABLED": "true", "OPENAI_API_KEY": "synthetic-key"}):
            content, metadata = generate_openai(self.request, [{"role": "user", "content": "synthetic request"}], factory)
        self.assertEqual(content, self.content)
        self.assertEqual(len(requests), 1)
        self.assertFalse(requests[0]["store"])
        self.assertTrue(requests[0]["text"]["format"]["strict"])
        schema = requests[0]["text"]["format"]["schema"]
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertEqual(metadata["usage"]["output_tokens"], 20)

    def test_refusal_or_incomplete_response_is_not_a_valid_draft(self):
        for status in ("incomplete", "completed"):
            factory = MagicMock()
            factory.return_value.__enter__.return_value.responses.parse.return_value = SimpleNamespace(status=status, output_parsed=None)
            with self.subTest(status=status), patch.dict(os.environ, {"AUTHORING_LLM_ENABLED": "true", "OPENAI_API_KEY": "synthetic-key"}):
                with self.assertRaises(GenerationError):
                    generate_openai(self.request, [], factory)

    def test_exported_authoring_schemas_match_models(self):
        for path, expected in artifacts().items():
            self.assertEqual(path.read_text(encoding="utf-8"), expected)


class AuthoringRunTests(unittest.TestCase):
    def setUp(self):
        self.request = DraftRequest.model_validate(load_json(ROOT / "content/authoring/configs/a02.v1.json"))
        # Keep isolated artifacts instead of deleting files; this workspace forbids deletion.
        self.store = RunStore(ROOT / "artifacts/authoring-tests" / uuid4().hex)

    def create(self):
        return create_run(self.request, "run", "pilot_replay", store=self.store)

    def test_run_is_replayable_and_overwrite_is_rejected_before_model_call(self):
        path, manifest = self.create()
        self.assertEqual(manifest["status"], "draft_ready")
        self.assertEqual(verify_run(path)["status"], "draft_ready")
        self.assertIsNone(load_json(path / "review-template.json")["reviewer"])
        factory = MagicMock()
        with self.assertRaises(FileExistsError):
            create_run(self.request, "run", "openai", store=self.store, client_factory=factory)
        factory.assert_not_called()

    def test_modified_artifact_is_detected(self):
        path, _ = self.create()
        with (path / "draft.json").open("a", encoding="utf-8") as stream:
            stream.write("\n")
        with self.assertRaises(ValueError):
            verify_run(path)

    def test_model_failure_has_safe_manifest_and_is_not_reviewable(self):
        with patch.dict(os.environ, {"AUTHORING_LLM_ENABLED": "false"}):
            path, manifest = create_run(self.request, "failed", "openai", store=self.store)
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["generation"]["model_call_attempts"], 0)
        self.assertTrue((path / "failure.json").exists())
        with self.assertRaises(ValueError):
            verify_run(path)

    def test_bad_math_replay_persists_failed_checks_instead_of_approving(self):
        _, bank = load_curriculum()
        content, _ = pilot_replay(self.request, bank)
        data = content.model_dump(mode="json")
        data["problems"][0]["reference_answer"] = "999"
        self.store.root.mkdir(parents=True)
        source = self.store.root / "synthetic-payload.json"
        self.store.write(source, data)
        path, manifest = create_run(self.request, "bad-math", "replay", input_path=source, store=self.store)
        self.assertEqual(manifest["status"], "check_failed")
        self.assertFalse(load_json(path / "checks.json")["passed"])
        self.assertEqual(load_json(path / "draft.json")["review"]["status"], "draft")
        self.assertEqual(verify_run(path)["status"], "check_failed")

    def test_review_context_change_is_detected_before_creating_approval(self):
        path, _ = self.create()
        pack = ConceptPack.model_validate(load_json(path / "draft.json"))
        review = ContentReview.model_validate({**review_template(pack), "review_id": "synthetic-review",
            "reviewer": "Synthetic independent reviewer", "reviewed_at": datetime.now(timezone.utc),
            "decision": "changes_requested", "comments": "Synthetic context drift test."})
        registry, bank = load_curriculum()
        changed = registry.model_copy(update={"content_version": "new-context"})
        with patch("app.authoring_runs.load_curriculum", return_value=(changed, bank)):
            with self.assertRaises(ValueError):
                review_run("run", review, store=self.store)
        self.assertFalse((path / "reviews").exists())

    def test_path_escape_and_runtime_bank_destination_are_rejected(self):
        with self.assertRaises(ValueError):
            RunStore(ROOT / "content/curriculum")
        for run_id in ("../escape", "C:/escape", "a/b", "."):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                self.store.path(run_id)

    def test_review_creates_separate_snapshot_and_preserves_original_draft(self):
        path, _ = self.create()
        original = (path / "draft.json").read_bytes()
        pack = ConceptPack.model_validate(load_json(path / "draft.json"))
        review = ContentReview.model_validate({**review_template(pack), "review_id": "synthetic-review",
            "reviewer": "Synthetic independent reviewer", "reviewed_at": datetime.now(timezone.utc),
            "decision": "approved", "checklist": {k: "pass" for k in review_template(pack)["checklist"]},
            "comments": "Synthetic lifecycle test; not actual content approval."})
        destination, approved = review_run("run", review, store=self.store)
        self.assertTrue(approved)
        self.assertTrue((destination / "approved-pack.json").exists())
        self.assertEqual((path / "draft.json").read_bytes(), original)
        with self.assertRaises(FileExistsError):
            review_run("run", review, store=self.store)

    def test_manifest_cannot_reference_arbitrary_files(self):
        path, manifest = self.create()
        manifest["artifact_sha256"]["../../secret.json"] = "0" * 64
        with patch("app.authoring_runs.load_json", return_value=manifest):
            with self.assertRaises(ValueError):
                verify_run(path)


if __name__ == "__main__":
    unittest.main()
