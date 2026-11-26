"""Check the Stage 1 confirmation, contracts, fixtures and generated coverage."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/authoring"))

from app.content_authoring import ContentReview, DraftRequest, apply_review, digest
from app.contracts import ContentBank
from app.curriculum import CURRENT_CURRICULUM_REVISION, ConceptPack, CurriculumRegistry, PilotBank, load_curriculum
from app.math_validator import VERSION as VALIDATOR_VERSION
from app.member2_contracts import FoundationExamples, ServerRetrievalScope
from app.member2_foundation import load_workboard, public_problem_examples
from app.member2_problem_contract import (
    VERSION as PUBLIC_PROBLEM_VERSION, PublicProblemExamples, demo_validator_task,
    project_curriculum_problem, project_legacy_problem,
)
from app.member2_runtime import demo_catalog
from app.member2_stage1 import add_pack_inventory, apply_update_confirmation, confirmed_coverage, render_confirmed_coverage
from prepare_member2_pilot import SOURCE as DRAFT_SOURCE, rendered_pilot

EXAMPLES = ROOT / "contracts/member2/v0.2.0/examples.json"
SCHEMA = ROOT / "contracts/member2/v0.2.0/FoundationExamples.schema.json"
PUBLIC_V3 = ROOT / "contracts/member2/v0.3.0"
COVERAGE = ROOT / "docs/implementation/member2/part1/coverage.json"
COVERAGE_MD = ROOT / "docs/implementation/member2/part1/coverage.md"
MEMBER2_RELEASE = ROOT / "content/authoring/batches/member2-original.v2"


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def check_examples(registry=None, bank=None):
    if registry is None or bank is None:
        registry, bank = load_curriculum()
    examples = FoundationExamples.model_validate_json(EXAMPLES.read_text(encoding="utf-8"))
    if [p.model_dump(mode="json") for p in examples.problems] != public_problem_examples(registry, bank):
        raise ValueError("Public problem fixtures no longer match the authoring projections")
    concepts = {c.concept_id: c for c in registry.concepts}
    for exchange in examples.retrieval_exchanges:
        ServerRetrievalScope.from_registry(registry, **exchange.request.scope.model_dump())
        query = exchange.request.query
        if query.target_skill_id not in {s.skill_id for s in concepts[query.concept_id].skills}:
            raise ValueError("Retrieval fixture references an unknown concept/skill mapping")
    return examples


def approved_member2_bank(baseline):
    """Verify the user-approved release against all 13 checked authoring drafts."""
    artifacts, summary = rendered_pilot("v2")
    manifest = json.loads((MEMBER2_RELEASE / "manifest.json").read_bytes())
    paths = ("registry-snapshot.json", "approved-bank.json")
    files = {name: (MEMBER2_RELEASE / name).read_bytes() for name in paths}
    if (manifest["basis"] != "user_confirmed_approval" or manifest["review_status"] != "human_approved"
            or manifest["runtime_publication"] is not False or manifest["revision"] != "M2-ORIG02"
            or manifest["content_version"] != summary["content_version"]
            or manifest["source_sha256"] != summary["source_sha256"]
            or manifest["files_sha256"] != {name: sha256(raw).hexdigest() for name, raw in files.items()}
            or json.loads(files["registry-snapshot.json"]) != artifacts["registry-snapshot.json"]):
        raise ValueError("The Member 2 approval manifest does not match the versioned source")
    registry = CurriculumRegistry.model_validate_json(files["registry-snapshot.json"])
    bank = PilotBank.model_validate_json(files["approved-bank.json"])
    expected_ids = set(summary["member2_concepts"])
    if set(manifest["packs"]) != expected_ids or {pack.concept_id for pack in bank.packs} != expected_ids:
        raise ValueError("The approval must cover exactly the assigned Member 2 concepts")
    for approved in bank.packs:
        cid = approved.concept_id
        entry = manifest["packs"][cid]
        review = ContentReview.model_validate(entry["review"])
        request = DraftRequest.model_validate(artifacts[f"{cid}/request.json"])
        draft = ConceptPack.model_validate(artifacts[f"{cid}/draft.json"])
        material_hash = sha256(artifacts[f"{cid}/review.md"].encode("utf-8")).hexdigest()
        if (review.review_id != manifest["record_id"] or review.model_dump(mode="json")["reviewed_at"] != manifest["recorded_at"]
                or entry["review_material_sha256"] != material_hash
                or entry["approved_pack_sha256"] != digest(approved.model_dump(mode="json"))
                or apply_review(draft, review, request, registry, baseline) != approved):
            raise ValueError(f"Approved Member 2 pack differs from its review: {cid}")
    return bank


def rendered_artifacts():
    check_examples()
    revision = CURRENT_CURRICULUM_REVISION
    registry, bank = load_curriculum(revision=revision)
    workboard = load_workboard()
    legacy = ContentBank.model_validate_json((ROOT / "content/linear_equations.v1.json").read_bytes())
    parameters = json.loads((ROOT / "content/bkt.bootstrap.v1.json").read_text(encoding="utf-8"))
    evidence = workboard.runtime_evidence
    if (parameters["skill_id"] != evidence.legacy_skill_id
            or any(p.concept_id != evidence.legacy_concept_id or
                   p.primary_skill_id != evidence.legacy_skill_id or
                   demo_validator_task(legacy.topic_id, p.to_public().model_dump(), p.primary_skill_id)
                   not in evidence.task_kinds for p in legacy.problems)):
        raise ValueError("Legacy evidence changed; review the workboard before regenerating")
    report = confirmed_coverage(registry, bank)
    report["current_validator_version"] = VALIDATOR_VERSION
    report["recorded_validator_version_matches"] = evidence.validator_version == VALIDATOR_VERSION
    draft_artifacts, draft_summary = rendered_pilot()
    drafts = PilotBank.model_validate(draft_artifacts["draft-bank.json"])
    member2_drafts = [pack for pack in drafts.packs if pack.concept_id in draft_summary["member2_concepts"]]
    canonical_source = f"content/curriculum/pilot.{revision}.json"
    member2_manifest = (MEMBER2_RELEASE / "manifest.json").relative_to(ROOT).as_posix()
    draft_source = DRAFT_SOURCE.relative_to(ROOT).as_posix()
    add_pack_inventory(report, {
        "Pilot canonical": (canonical_source, bank.packs),
        "Nháp Member 2": (draft_source, member2_drafts),
        "13 pack Member 2 đã duyệt": (member2_manifest, approved_member2_bank(bank).packs),
    })
    demo_tasks = {}
    for item in demo_catalog().values():
        demo_tasks.setdefault(item.public["concept_id"], set()).add(item.public["task"]["kind"])
    report["summary"]["demo_concepts_supported"] = len(demo_tasks)
    for row in report["concepts"]:
        task_kinds = demo_tasks.get(row["concept_id"])
        row["internal_demo"] = {"validator_task_kinds": sorted(task_kinds), "assessment_scope": "final_answer"} if task_kinds else None
    for relative in (f"content/curriculum/registry.{revision}.json", canonical_source, draft_source,
                     member2_manifest):
        report["input_sha256"][relative] = sha256((ROOT / relative).read_bytes()).hexdigest()
    problems_by_kind = {}
    for pack in [*bank.packs, *member2_drafts]:
        for problem in pack.problems:
            if problem.task.kind not in problems_by_kind:
                problems_by_kind[problem.task.kind] = project_curriculum_problem(problem, pack.content_version)
    examples = PublicProblemExamples(
        curriculum_drafts=[problems_by_kind[kind] for kind in sorted(problems_by_kind)],
        legacy_demo=project_legacy_problem(legacy.problems[0].to_public()),
    )
    report["public_problem_contract"] = {"version": PUBLIC_PROBLEM_VERSION,
                                         "fixture_task_kinds": sorted(problems_by_kind)}
    apply_update_confirmation(report)
    return {
        "schema": (SCHEMA, json_text(FoundationExamples.model_json_schema())),
        "problem-schema": (PUBLIC_V3 / "PublicProblemExamples.schema.json", json_text(PublicProblemExamples.model_json_schema())),
        "problem-examples": (PUBLIC_V3 / "examples.json", json_text(examples.model_dump(mode="json"))),
        "coverage-json": (COVERAGE, json_text(report)),
        "coverage-md": (COVERAGE_MD, render_confirmed_coverage(report)),
    }, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", choices=["schema", "problem-schema", "problem-examples", "coverage-json", "coverage-md"])
    args = parser.parse_args()
    artifacts, report = rendered_artifacts()
    if args.render:
        print(artifacts[args.render][1], end="")
        return
    errors = [str(p.relative_to(ROOT)) for p, content in artifacts.values()
              if not p.exists() or p.read_text(encoding="utf-8") != content]
    if errors:
        raise SystemExit("Stale or missing generated artifacts: " + ", ".join(errors))
    print("PASS: Member 2 Stage 1 confirmation, schemas, synthetic fixtures and coverage are consistent")
    print(json.dumps(report["summary"], ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
