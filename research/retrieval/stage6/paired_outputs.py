"""Paired Full/No-RAG runs of the current product graph, without model APIs or session writes."""
from copy import deepcopy
import random
from time import perf_counter
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from app import teaching_runtime
from app.manage import digest
from app.member2_runtime import demo_catalog
from app.tutor import build_graph
from research.retrieval.dataset import json_bytes, require, sha256

CRITERIA = {
    "mathematics": "0=sai; 1=chưa đủ rõ để xác nhận; 2=đúng toán",
    "error_alignment": "0=không bám lỗi; 1=một phần; 2=trực tiếp; null=N/A khi không có bài nộp sai",
    "support_level": "0=sai mức hỗ trợ; 1=một phần; 2=phù hợp",
    "answer_disclosure": "0=không tiết lộ; 1=có nguy cơ/một phần; 2=tiết lộ đáp án bài đang đo",
}


def assessment_signature(assessment):
    """Compare grading facts; retain each invocation's correlation ID in the raw output."""
    return {key: value for key, value in assessment.items() if key != "assessment_id"}


def scenarios(bank, snapshot_id):
    catalog = demo_catalog()
    output = []
    for pack in sorted(bank.packs, key=lambda pack: pack.concept_id):
        specs = [(f"hint-{level}", pack.problems[(level - 1) * 2], "request_hint", [], level - 1)
                 for level in (1, 2, 3)]
        specs += [("explanation", pack.problems[0], "request_explanation", [], 0),
                  ("example", pack.problems[0], "request_example", [], 0)]
        by_id = {problem.case_id: problem for problem in pack.problems}
        specs += [("wrong-" + error.error_id, by_id[error.problem_id], "submit", error.response_steps, 0)
                  for error in pack.errors]
        for suffix, problem, action, steps, level in specs:
            scenario_id = f"M2S6-{pack.concept_id}-{suffix}"
            item = catalog[(problem.case_id, pack.content_version)]
            state = {"problem": deepcopy(item.private), "action": action, "steps": list(steps),
                "opportunity": {"assistance_level": level, "no_progress_count": 0,
                                "best_progress": 0, "assistance_received": level > 0},
                "observed": False, "near": False, "llm_allowed": False,
                "teaching": {"snapshot_id": snapshot_id,
                    "session_id": str(uuid5(NAMESPACE_URL, scenario_id + "/session")),
                    "opportunity_id": str(uuid5(NAMESPACE_URL, scenario_id + "/opportunity")),
                    "problem_id": problem.case_id, "concept_id": pack.concept_id,
                    "skill_id": problem.primary_skill_id, "family_id": problem.family_id,
                    "source_group": problem.source_group, "difficulty": problem.difficulty,
                    "content_version": pack.content_version}}
            output.append({"scenario_id": scenario_id, "concept_id": pack.concept_id,
                           "scenario_class": "wrong_submission" if action == "submit" else "support_request",
                           "common_state": state, "common_state_sha256": digest(state)})
    return output


def run_pairs(bank, snapshot_id, progress=None):
    graph = build_graph()
    pairs = []
    for index, scenario in enumerate(scenarios(bank, snapshot_id)):
        common = scenario["common_state"]
        variants = {}
        for mode in ("full", "no_rag"):
            state = deepcopy(common)
            state["teaching"]["mode"] = mode
            if mode == "no_rag":
                state["teaching"]["snapshot_id"] = None
            started = perf_counter()
            if mode == "no_rag":
                with patch.object(teaching_runtime, "connect", side_effect=AssertionError("No-RAG content access")) as spy:
                    result = graph.invoke(state)
                    require(spy.call_count == 0, "No-RAG touched the content store")
            else:
                result = graph.invoke(state)
            elapsed = (perf_counter() - started) * 1000
            require(result["eligibility_preview"] == {"eligible": False, "reason": "not_target_evidence"},
                    "Canonical paired scenarios unexpectedly produced BKT evidence")
            if mode == "full":
                require(result["response"]["response_source"] == "reviewed_kb", "Full did not deliver reviewed context")
                require(result["response"]["content_refs"], "Full lacks a delivered content reference")
            else:
                require(not result["response"]["content_refs"] and not result["teaching_context"], "No-RAG kept context")
            variants[mode] = {"response": result["response"], "policy": result["policy"],
                              "assessment": result["validation"]["assessment"],
                              "eligibility": result["eligibility_preview"], "elapsed_ms": elapsed}
        require(assessment_signature(variants["full"]["assessment"]) ==
                assessment_signature(variants["no_rag"]["assessment"]), "Paired assessment facts differ")
        require(variants["full"]["policy"] == variants["no_rag"]["policy"], "Paired pedagogical policies differ")
        require(digest(common) == scenario["common_state_sha256"], "Generator mutated the common scenario")
        pairs.append({key: value for key, value in scenario.items() if key != "common_state"} | {
            "prompt": common["problem"]["prompt"], "steps": common["steps"], "action": common["action"],
            "prior_hint_level": common["opportunity"]["assistance_level"], "variants": variants,
            "same_message": variants["full"]["response"]["message"] == variants["no_rag"]["response"]["message"]})
        if progress and (index + 1) % 13 == 0:
            progress({"stage": "paired_outputs", "completed": index + 1})
    return pairs


def blind_packet(pairs, seed):
    rng = random.Random(seed)
    order = list(pairs)
    rng.shuffle(order)
    public, key = [], []
    for index, pair in enumerate(order, 1):
        modes = ["full", "no_rag"]
        rng.shuffle(modes)
        pair_id = f"PAIR-{index:04}"
        public.append({"pair_id": pair_id, "prompt": pair["prompt"], "learner_steps": pair["steps"],
            "request_action": pair["action"], "prior_hint_level": pair["prior_hint_level"],
            "error_alignment_applicable": pair["scenario_class"] == "wrong_submission",
            "responses": {label: pair["variants"][mode]["response"]["message"] for label, mode in zip(("A", "B"), modes)}})
        key.append({"pair_id": pair_id, "scenario_id": pair["scenario_id"], "concept_id": pair["concept_id"],
                    "common_state_sha256": pair["common_state_sha256"], "configuration_by_label": dict(zip(("A", "B"), modes))})
    packet = {"status": "pending_independent_ratings", "pairs": public}
    template = {"schema_version": "1.0.0", "packet_sha256": sha256(json_bytes(packet)),
                "reviewer": None, "reviewed_at": None, "method": "independent_human", "criteria": CRITERIA,
                "pairs": [{"pair_id": row["pair_id"], "responses": {
                    label: {"scores": {criterion: None for criterion in CRITERIA}, "notes": ""}
                    for label in ("A", "B")}} for row in public]}
    return packet, key, template


def summarize_pairs(pairs):
    return {"pair_count": len(pairs), "concept_count": len({pair["concept_id"] for pair in pairs}),
            "wrong_submission_pairs": sum(pair["scenario_class"] == "wrong_submission" for pair in pairs),
            "identical_messages": sum(pair["same_message"] for pair in pairs),
            "different_messages": sum(not pair["same_message"] for pair in pairs),
            "generator": "current_product_reviewed_text_assembler_no_free_form_llm",
            "same_assessment_and_policy": True, "assessment_comparison": "all_fields_except_assessment_id",
            "session_writes": 0, "model_api_calls": 0,
            "quality_ratings": None, "quality_status": "pending_independent_human_review",
            "interpretation": "Identical hints are expected: the no_rag baseline already contains the approved hint ladder. "
                              "Message differences do not establish improved teaching quality or learning outcomes."}
