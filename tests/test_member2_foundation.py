"""Contract boundary/semantic regression tests. No model, database or temporary files."""
import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/checks"))

from app.curriculum import load_curriculum
from app.knowledge import eligibility
from app.member2_contracts import (
    ConceptReadiness, CurriculumProblemPublic, FoundationExamples, LearningReportSnapshot,
    OpportunityAssistance, RetrievalExchange, RetrievalQuery, RetrievalRequest,
    ServerRetrievalScope, TutorPresentation, project_problem,
)
from app.member2_foundation import Workboard, build_coverage, load_workboard, public_problem_examples
from app import member2_stage1
from check_member2_foundation import rendered_artifacts

FIXTURES = json.loads((ROOT / "contracts/member2/v0.2.0/examples.json").read_text(encoding="utf-8"))


class Member2ContractTests(unittest.TestCase):
    def exchange(self):
        return copy.deepcopy(FIXTURES["retrieval_exchanges"][0])

    def test_examples_cover_all_five_supported_authoring_task_types(self):
        models = FoundationExamples.model_validate(FIXTURES)
        self.assertEqual({p.task.kind for p in models.problems},
                         {"numeric", "evaluate", "polynomial", "linear_equation", "quadratic_vertex"})
        self.assertEqual([p.model_dump(mode="json") for p in models.problems], public_problem_examples())

    def test_private_authoring_fields_are_not_projected_or_accepted(self):
        registry, bank = load_curriculum()
        for pack in bank.packs:
            for problem in pack.problems:
                public = project_problem(problem, pack.content_version).model_dump(mode="json")
                with self.subTest(problem=problem.case_id):
                    for field in ("reference_answer", "reference_steps", "source_group", "review", "origin"):
                        self.assertNotIn(field, public)
                    for field in ("reference_answer", "reference_steps"):
                        with self.assertRaises(ValidationError):
                            CurriculumProblemPublic.model_validate({**public, field: getattr(problem, field)})
        self.assertEqual(len(registry.concepts), 40)

    def test_public_task_requires_substitution_only_when_applicable(self):
        problem = copy.deepcopy(next(p for p in FIXTURES["problems"] if p["task"]["kind"] == "evaluate"))
        problem["task"]["variable_value"] = None
        with self.assertRaises(ValidationError):
            CurriculumProblemPublic.model_validate(problem)
        problem["task"].update(kind="numeric", variable_value="2")
        with self.assertRaises(ValidationError):
            CurriculumProblemPublic.model_validate(problem)

    def test_student_query_cannot_override_server_scope_or_request_private_content(self):
        query = self.exchange()["request"]["query"]
        for field, value in [("allowed_hint_level", 3), ("review_status", "draft"),
                             ("scope", {}), ("purpose", "reference_solution")]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                RetrievalQuery.model_validate({**query, field: value})

    def test_query_cannot_select_a_concept_or_skill_outside_server_permissions(self):
        for field, value in [("concept_id", "N01"), ("target_skill_id", "SK-N01-SIGNED-ADD")]:
            data = self.exchange()
            data["request"]["query"][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                RetrievalExchange.model_validate(data)

    def test_allowed_targets_do_not_authorize_their_cross_product(self):
        data = self.exchange()
        data["request"]["scope"]["allowed_targets"].append({"concept_id": "N01", "skill_id": "SK-N01-SIGNED-ADD"})
        data["request"]["query"]["target_skill_id"] = "SK-N01-SIGNED-ADD"
        data["result"]["chunks"][0]["skill_ids"] = ["SK-N01-SIGNED-ADD"]
        with self.assertRaises(ValidationError):
            RetrievalExchange.model_validate(data)

    def test_server_scope_factory_checks_every_pair_against_registry(self):
        registry, _ = load_curriculum()
        base = self.exchange()["request"]["scope"]
        for target in ({"concept_id": "A02", "skill_id": "SK-N01-SIGNED-ADD"},
                       {"concept_id": "N01", "skill_id": "SK-missing"}):
            data = copy.deepcopy(base)
            data["allowed_targets"].append(target)
            with self.subTest(target=target), self.assertRaises(ValueError):
                ServerRetrievalScope.from_registry(registry, **data)
        data = copy.deepcopy(base)
        data["allowed_targets"].append({"concept_id": "N01", "skill_id": "SK-N01-SIGNED-ADD"})
        scope = ServerRetrievalScope.from_registry(registry, **data)
        request = self.exchange()["request"]
        request["scope"] = scope.model_dump(mode="json")
        request["query"].update(concept_id="N01", target_skill_id="SK-N01-SIGNED-ADD")
        self.assertEqual(RetrievalRequest.model_validate(request).query.concept_id, "N01")

    def test_scope_rejects_duplicate_pairs_and_legacy_independent_lists(self):
        for mutation in ("duplicate", "legacy", "empty"):
            scope = self.exchange()["request"]["scope"]
            if mutation == "duplicate": scope["allowed_targets"] *= 2
            elif mutation == "empty": scope["allowed_targets"] = []
            else:
                scope["allowed_concept_ids"] = ["A02"]
                scope["allowed_skill_ids"] = ["SK-A02-DISTRIBUTE"]
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                ServerRetrievalScope.model_validate(scope)

    def test_retrieval_enforces_identity_purpose_grade_and_difficulty(self):
        mutations = [("concept_id", "N01"), ("skill_ids", ["SK-missing"]),
                     ("grade_levels", [11]), ("difficulty", "standard")]
        for key, value in mutations:
            data = self.exchange()
            data["result"]["chunks"][0][key] = value
            with self.subTest(field=key), self.assertRaises(ValidationError):
                RetrievalExchange.model_validate(data)
        data = self.exchange()
        data["request"]["query"]["purpose"] = "example"
        with self.assertRaises(ValidationError):
            RetrievalExchange.model_validate(data)

    def test_disclosure_ceiling_and_level_four_are_rejected(self):
        data = self.exchange()
        data["result"]["chunks"][0].update(hint_level=2, disclosure="strategy")
        with self.assertRaises(ValidationError):
            RetrievalExchange.model_validate(data)
        for value in (4, True, "1"):
            data = self.exchange()
            data["request"]["scope"]["allowed_hint_level"] = value
            with self.subTest(level=value), self.assertRaises(ValidationError):
                RetrievalExchange.model_validate(data)

    def test_draft_review_and_missing_provenance_cannot_be_retrieved(self):
        for mutation in ({"status": "draft"}, {"human_reviewer": None}, {"reviewed_at": None}):
            data = self.exchange()
            data["result"]["chunks"][0]["review"].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                RetrievalExchange.model_validate(data)

    def test_current_problem_and_near_example_are_excluded(self):
        for key, value in [("problem_id", "P-A02-01"), ("source_group", "GROUP-A02-positive")]:
            data = copy.deepcopy(FIXTURES["retrieval_exchanges"][1])
            data["result"]["chunks"][0][key] = value
            with self.subTest(field=key), self.assertRaises(ValidationError):
                RetrievalExchange.model_validate(data)
        data = copy.deepcopy(FIXTURES["retrieval_exchanges"][1])
        data["result"]["chunks"][0]["source_group"] = None
        with self.assertRaises(ValidationError):
            RetrievalExchange.model_validate(data)

    def test_retrieved_chunk_rejects_private_fields(self):
        data = self.exchange()
        data["result"]["chunks"][0]["reference_answer"] = "private"
        with self.assertRaises(ValidationError):
            RetrievalExchange.model_validate(data)

    def test_retrieval_correlates_request_snapshot_and_limit(self):
        for key, value in [("request_id", "00000000-0000-4000-8000-000000000099"),
                           ("kb_snapshot_version", "other-snapshot")]:
            data = self.exchange()
            data["result"][key] = value
            with self.subTest(field=key), self.assertRaises(ValidationError):
                RetrievalExchange.model_validate(data)
        data = self.exchange()
        data["request"]["query"]["top_k"] = 1
        extra = {**data["result"]["chunks"][0], "content_id": "ANOTHER"}
        data["result"]["chunks"].append(extra)
        with self.assertRaises(ValidationError):
            RetrievalExchange.model_validate(data)

    def test_empty_result_duplicate_and_semantic_version_rules(self):
        for mutation in ("empty_without_reason", "nonempty_with_reason", "duplicate", "no_embedding", "nonfinite"):
            data = self.exchange()
            if mutation == "empty_without_reason": data["result"]["chunks"] = []
            elif mutation == "nonempty_with_reason": data["result"]["fallback_reason"] = "no_eligible_content"
            elif mutation == "duplicate": data["result"]["chunks"] *= 2
            elif mutation == "no_embedding": data["result"]["embedding_version"] = None
            else: data["result"]["elapsed_ms"] = float("nan")
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                RetrievalExchange.model_validate(data)

    def test_different_example_requires_separate_public_task(self):
        data = copy.deepcopy(FIXTURES["tutor_presentations"][1])
        data["different_example"] = None
        with self.assertRaises(ValidationError):
            TutorPresentation.model_validate(data)

    def test_different_example_cannot_be_the_current_problem(self):
        data = copy.deepcopy(FIXTURES["tutor_presentations"][1])
        data["different_example"]["problem_id"] = data["active_problem_id"]
        with self.assertRaises(ValidationError):
            TutorPresentation.model_validate(data)

    def test_draft_template_cannot_be_labelled_reviewed_fallback(self):
        data = copy.deepcopy(FIXTURES["tutor_presentations"][2])
        data["response_source"] = "reviewed_fallback"
        with self.assertRaises(ValidationError):
            TutorPresentation.model_validate(data)

    def assistance_state(self):
        return OpportunityAssistance(
            opportunity_id=FIXTURES["tutor_presentations"][0]["opportunity_id"],
            problem_id="P-A02-01", target_skill_id="SK-A02-DISTRIBUTE",
            assistance_level=0, assistance_received=False,
        )

    def test_level_zero_explanation_is_assistance_only_when_delivered(self):
        state = self.assistance_state()
        exchange = RetrievalExchange.model_validate(FIXTURES["retrieval_exchanges"][4])
        self.assertEqual(exchange.result.chunks[0].hint_level, 0)
        self.assertTrue(exchange.result.chunks[0].counts_as_assistance)
        self.assertFalse(state.assistance_received)  # A read-only retrieval is not delivery.
        presentation = TutorPresentation.model_validate(FIXTURES["tutor_presentations"][3])
        updated = state.record_delivery(presentation)
        self.assertEqual(updated.assistance_level, 0)
        self.assertTrue(updated.assistance_received)
        assessment = {"assessment_status": "verified_correct", "primary_skill_id": state.target_skill_id}
        self.assertEqual(eligibility(assessment, {**updated.model_dump(), "relation": "initial"}),
                         {"eligible": False, "reason": "assisted"})

    def test_delivered_assistance_is_sticky_idempotent_and_keeps_maximum_level(self):
        state = self.assistance_state()
        hint = TutorPresentation.model_validate(FIXTURES["tutor_presentations"][1])
        neutral = TutorPresentation.model_validate(FIXTURES["tutor_presentations"][4])
        helped = state.record_delivery(hint)
        self.assertEqual(helped, helped.record_delivery(hint))
        after_neutral = helped.record_delivery(neutral)
        self.assertTrue(after_neutral.assistance_received)
        self.assertEqual(after_neutral.assistance_level, 3)
        self.assertFalse(state.assistance_received)

    def test_delivery_rejects_wrong_opportunity_even_for_the_same_problem(self):
        for key, value in (("opportunity_id", "00000000-0000-4000-8000-000000000099"),
                           ("active_problem_id", "OTHER-PROBLEM")):
            data = copy.deepcopy(FIXTURES["tutor_presentations"][3])
            data[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.assistance_state().record_delivery(TutorPresentation.model_validate(data))

    def test_teaching_response_cannot_deny_assistance_even_at_level_zero(self):
        for index in (0, 1, 3):
            data = copy.deepcopy(FIXTURES["tutor_presentations"][index])
            data["assistance_provided"] = False
            with self.subTest(presentation=index), self.assertRaises(ValidationError):
                TutorPresentation.model_validate(data)
        data = self.exchange()
        data["result"]["chunks"][0]["counts_as_assistance"] = False
        with self.assertRaises(ValidationError):
            RetrievalExchange.model_validate(data)
        with self.assertRaises(ValidationError):
            OpportunityAssistance.model_validate({**self.assistance_state().model_dump(), "assistance_level": 1})

    def test_format_clarification_does_not_disqualify_independent_work(self):
        state = self.assistance_state().record_delivery(
            TutorPresentation.model_validate(FIXTURES["tutor_presentations"][4]))
        assessment = {"assessment_status": "verified_correct", "primary_skill_id": state.target_skill_id}
        self.assertTrue(eligibility(assessment, {**state.model_dump(), "relation": "initial"})["eligible"])

    def test_new_feedback_does_not_retroactively_assist_the_first_submission(self):
        state = self.assistance_state()
        first = {"assessment_status": "verified_incorrect", "primary_skill_id": state.target_skill_id}
        first_eligibility = eligibility(first, {**state.model_dump(), "relation": "initial"})
        after_feedback = state.record_delivery(TutorPresentation.model_validate(FIXTURES["tutor_presentations"][3]))
        corrected = {**first, "assessment_status": "verified_correct"}
        next_eligibility = eligibility(corrected, {**after_feedback.model_dump(), "relation": "initial"})
        self.assertTrue(first_eligibility["eligible"])
        self.assertEqual(next_eligibility, {"eligible": False, "reason": "assisted"})

    def test_legacy_eligibility_precedence_stays_unchanged(self):
        base = {"target_skill_id": "SK-LIN-SOLVE", "assistance_level": 0, "relation": "initial"}
        assessment = {"assessment_status": "verified_correct", "primary_skill_id": "SK-LIN-SOLVE"}
        cases = [({}, {}, "first_independent_verified"), ({"assistance_level": 1}, {}, "assisted"),
                 ({"assistance_received": True}, {}, "assisted"),
                 ({"assistance_received": True}, {"observed": True}, "already_observed"),
                 ({"relation": "repeat"}, {}, "repeat"), ({}, {"near": True}, "near_practice")]
        for extra, options, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(eligibility(assessment, {**base, **extra}, **options)["reason"], expected)

    def test_report_assisted_outcome_does_not_inflate_observation_count(self):
        report = LearningReportSnapshot.model_validate(FIXTURES["reports"][0])
        self.assertEqual(report.assisted_correct, 1)
        self.assertEqual(report.valid_observations, 1)
        self.assertLess(report.skills[0].mastery_after, report.skills[0].mastery_before)
        self.assertEqual(report.skills[0].evidence_count_after, 1)

    def test_report_accepts_two_own_observations_and_one_interleaved_observation(self):
        report = LearningReportSnapshot.model_validate(FIXTURES["reports"][3])
        skill = report.skills[0]
        self.assertEqual((skill.evidence_count_before, skill.evidence_count_after), (5, 8))
        self.assertEqual((skill.session_observations, skill.other_session_observations), (2, 1))
        self.assertEqual(len(skill.session_observation_ids), report.valid_observations)
        self.assertEqual(report.valid_observations, 2)

    def test_report_rejects_missing_duplicate_or_miscounted_observation_ids(self):
        for mutation in ("missing", "duplicate", "count", "other_count", "backwards"):
            data = copy.deepcopy(FIXTURES["reports"][3])
            skill = data["skills"][0]
            if mutation == "missing": skill["session_observation_ids"] = []
            elif mutation == "duplicate": skill["session_observation_ids"] *= 2
            elif mutation == "count": skill["session_observations"] = 3
            elif mutation == "other_count": skill["other_session_observations"] = 0
            else: skill["evidence_count_after"] = 4
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                LearningReportSnapshot.model_validate(data)

    def test_one_observation_cannot_be_reported_as_evidence_for_two_skills(self):
        data = copy.deepcopy(FIXTURES["reports"][0])
        second = {**data["skills"][0], "concept_id": "N01", "skill_id": "SK-N01-SIGNED-ADD"}
        data["skills"].append(second)
        data["valid_observations"] = 2
        with self.assertRaises(ValidationError):
            LearningReportSnapshot.model_validate(data)

    def test_session_without_own_observations_does_not_import_other_session_changes(self):
        data = copy.deepcopy(FIXTURES["reports"][2])
        data["skills"][0].update(other_session_observations=1, evidence_count_after=4)
        with self.assertRaises(ValidationError):
            LearningReportSnapshot.model_validate(data)

    def test_old_proposal_version_is_rejected_instead_of_silently_migrated(self):
        data = copy.deepcopy(FIXTURES["reports"][0])
        data["contract_version"] = "member2-proposal-0.1.0"
        with self.assertRaises(ValidationError):
            LearningReportSnapshot.model_validate(data)

    def test_report_rejects_fabricated_delta_and_inconsistent_totals(self):
        for mutation in ("delta", "count", "total", "duplicate", "future", "provenance", "negative", "boolean"):
            data = copy.deepcopy(FIXTURES["reports"][2])
            skill = data["skills"][0]
            if mutation == "delta": skill["mastery_after"] = .9
            elif mutation == "count": skill["evidence_count_after"] = 4
            elif mutation == "total": data["valid_observations"] = 1
            elif mutation == "duplicate": data["skills"] *= 2
            elif mutation == "future": skill["updated_at"] = "2026-11-17T10:00:00+07:00"
            elif mutation == "provenance": skill["parameter_version"] = None
            elif mutation == "negative": data["assisted_correct"] = -1
            else: data["valid_observations"] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                LearningReportSnapshot.model_validate(data)

    def test_empty_session_uses_unknown_mastery_or_unchanged_existing_snapshot(self):
        unknown = LearningReportSnapshot.model_validate(FIXTURES["reports"][1])
        existing = LearningReportSnapshot.model_validate(FIXTURES["reports"][2])
        self.assertIsNone(unknown.skills[0].mastery_after)
        self.assertEqual(existing.skills[0].mastery_before, existing.skills[0].mastery_after)


class Member2CoverageTests(unittest.TestCase):
    def test_inventory_counts_distinct_concepts_across_versions(self):
        _, report = rendered_artifacts()
        inventory = report["pack_inventory"]
        self.assertEqual([source["pack_count"] for source in inventory.values()], [10, 13, 13])
        self.assertEqual(report["summary"]["concepts_with_any_pack"], 20)
        self.assertEqual(report["summary"]["concepts_with_any_approved_pack"], 13)
        self.assertEqual(report["edge_review_counts"], {"draft": 68})
        rows = {row["concept_id"]: row for row in report["concepts"]}
        self.assertEqual(len(report["pack_inventory"]), 3)
        self.assertEqual(rows["F05"]["pack_sources"]["Nháp Member 2"]["task_kinds"], ["quadratic_axis", "quadratic_vertex"])
        self.assertEqual(rows["F05"]["pack_sources"]["13 pack Member 2 đã duyệt"]["review"]["status"], "human_approved")
        self.assertEqual(rows["F05"]["internal_demo"]["validator_task_kinds"], ["quadratic_axis", "quadratic_vertex"])
        self.assertEqual(report["summary"]["demo_concepts_supported"], 13)
        self.assertEqual(report["summary"]["ready_concepts"], 0)

    def test_expanded_public_fixtures_cover_all_tasks_and_preserve_legacy_ids(self):
        from pydantic import TypeAdapter
        from app.curriculum import AuthoringTaskKind
        from app.member2_problem_contract import PublicProblemExamples

        artifacts, report = rendered_artifacts()
        models = PublicProblemExamples.model_validate_json(artifacts["problem-examples"][1])
        actual = {problem.task.kind for problem in models.curriculum_drafts}
        self.assertEqual(actual, set(TypeAdapter(AuthoringTaskKind).json_schema()["enum"]))
        self.assertEqual(report["public_problem_contract"]["review_status"], "confirmed_by_team")
        for problem in models.curriculum_drafts:
            self.assertTrue({"reference_answer", "reference_steps", "source_group", "origin"}.isdisjoint(problem.model_dump()))
        legacy = models.legacy_demo
        self.assertEqual((legacy.concept_id, legacy.primary_skill_id, legacy.task.kind),
                         ("CON-LINEAR-01", "SK-LIN-SOLVE", "linear_equation"))

    def test_update_confirmation_is_scoped_and_does_not_change_readiness(self):
        _, report = rendered_artifacts()
        record = report["stage1_update_confirmation"]
        self.assertEqual(record["basis"], "user_attested_team_confirmation")
        with patch.object(member2_stage1, "update_scope_hashes", return_value=record["scope_sha256"]):
            member2_stage1.apply_update_confirmation(report)
        self.assertTrue(report["stage1_update_scope_matches"])
        self.assertEqual(record["confirmed_edge_count"], 68)
        self.assertEqual(record["confirmed_legacy_mapping_count"], len(report["legacy_mappings"]))
        self.assertEqual(report["summary"]["ready_concepts"], 0)
        self.assertTrue(all(mapping["status"] == "proposed" for mapping in report["legacy_mappings"]))

        modified = {**record, "scope_sha256": {}}
        with patch.object(member2_stage1, "UPDATE_CONFIRMATION") as path:
            path.read_bytes.return_value = json.dumps(modified).encode("utf-8")
            with self.assertRaisesRegex(ValueError, "recorded review scope"):
                member2_stage1.apply_update_confirmation(report)

        with patch.object(member2_stage1, "update_scope_hashes", return_value={}):
            member2_stage1.apply_update_confirmation(report)
        self.assertFalse(report["stage1_update_scope_matches"])
        self.assertEqual(report["public_problem_contract"]["review_status"], "pending_team_review")

    def test_team_confirmation_closes_contract_gate_without_publishing_content(self):
        _, report = rendered_artifacts()
        self.assertEqual(report["assignment_status"], "confirmed_by_team")
        self.assertEqual(report["summary"]["confirmed_assignments"], 40)
        self.assertEqual(report["summary"]["accepted_integration_gates"], 5)
        self.assertEqual(report["team_confirmation"]["basis"], "user_attested_team_confirmation")
        self.assertTrue(all(g["status"] == "accepted" and g["reviewed_by"] is None for g in report["integration_gates"]))
        self.assertTrue(all(row["readiness"]["contract_review_complete"] for row in report["concepts"]))
        self.assertEqual(report["summary"]["approved_packs"], 0)
        self.assertEqual(report["summary"]["public_chunks"], 0)
        self.assertEqual(report["summary"]["ready_concepts"], 0)

    def test_incomplete_signature_or_changed_scope_cannot_confirm_the_workboard(self):
        registry, bank = load_curriculum()
        original = json.loads(member2_stage1.CONFIRMATION.read_bytes())
        for field, value in (
            ("signature", " "),
            ("confirmed_members", ["Member 1", "Member 2", "Member 2"]),
            ("accepted_gates", original["accepted_gates"][:-1]),
            ("scope_sha256", {}),
        ):
            with self.subTest(field=field), patch.object(member2_stage1, "CONFIRMATION") as path:
                path.read_bytes.return_value = json.dumps({**original, field: value}).encode("utf-8")
                with self.assertRaises(ValueError):
                    member2_stage1.confirmed_coverage(registry, bank)

    def test_coverage_keeps_registry_drafts_and_runtime_readiness_distinct(self):
        report = build_coverage()
        summary = report["summary"]
        self.assertEqual((summary["registry_concepts"], summary["packs_present"], summary["problems"]), (40, 10, 60))
        self.assertEqual((summary["approved_packs"], summary["public_chunks"], summary["ready_concepts"]), (0, 0, 0))
        self.assertEqual(summary["proposed_owner_counts"], {"Member 1": 13, "Member 2": 13, "Member 3": 14})
        self.assertTrue(all(not r["readiness"]["validator_integrated"] for r in report["concepts"]))

    def test_workboard_rejects_overlap_self_review_missing_concept_and_fake_acceptance(self):
        base = load_workboard().model_dump(mode="json")
        for mutation in ("overlap", "self", "missing", "gate", "accept"):
            data = copy.deepcopy(base)
            if mutation == "overlap": data["assignments"][1]["concept_ids"][0] = data["assignments"][0]["concept_ids"][0]
            elif mutation == "self": data["assignments"][0]["reviewer"] = data["assignments"][0]["owner"]
            elif mutation == "missing": data["assignments"][0]["concept_ids"].pop()
            elif mutation == "gate": data["integration_gates"][0]["id"] = "MISSING"
            else: data["integration_gates"][0]["status"] = "accepted"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build_coverage(workboard=Workboard.model_validate(data))

    def test_draft_readiness_cannot_be_activated_with_client_ready_flag(self):
        data = copy.deepcopy(FIXTURES["readiness"][0])
        readiness = ConceptReadiness.model_validate(data)
        self.assertFalse(readiness.ready)
        self.assertIn("pack_approved", readiness.blockers)
        with self.assertRaises(ValidationError):
            ConceptReadiness.model_validate({**data, "ready": True})

    def test_human_content_review_alone_does_not_make_canonical_runtime_ready(self):
        registry, bank = load_curriculum()
        registry, bank = registry.model_copy(deep=True), bank.model_copy(deep=True)
        concept = next(c for c in registry.concepts if c.concept_id == "A02")
        pack = next(p for p in bank.packs if p.concept_id == "A02")
        for item in (concept.review, pack.review):
            item.status = "human_approved"
            item.human_reviewer = "synthetic-only"
            item.reviewed_at = datetime.fromisoformat("2026-11-16T09:00:00+07:00")
        concept.alignment.status = "human_approved"
        concept.alignment.reviewer = "synthetic-only"
        row = next(r for r in build_coverage(registry, bank)["concepts"] if r["concept_id"] == "A02")
        self.assertGreater(row["public_chunks"], 0)
        self.assertFalse(row["readiness"]["ready"])
        self.assertFalse(row["readiness"]["validator_integrated"])

    def test_approved_edge_to_draft_prerequisite_does_not_pass_readiness(self):
        registry, bank = load_curriculum()
        registry = registry.model_copy(deep=True)
        for edge in registry.edges:
            if edge.target_concept_id == "E02":
                edge.review.status = "human_approved"
                edge.review.human_reviewer = "synthetic-only"
                edge.review.reviewed_at = datetime.fromisoformat("2026-11-16T09:00:00+07:00")
        row = next(r for r in build_coverage(registry, bank)["concepts"] if r["concept_id"] == "E02")
        self.assertFalse(row["readiness"]["prerequisites_approved"])

    def test_generated_artifacts_match_current_sources_and_schema(self):
        artifacts, _ = rendered_artifacts()
        for name, (path, expected) in artifacts.items():
            with self.subTest(artifact=name):
                self.assertEqual(path.read_text(encoding="utf-8"), expected)


if __name__ == "__main__":
    unittest.main()
