"""Kiểm và (tùy chọn) xuất nháp nội dung tự soạn của Member 1, theo đúng đường của Member 2 và 3.

Dùng lại ``make_pack``/``review_material`` của ``prepare_member2_pilot.py`` và ``check_draft`` của
pipeline biên soạn. Không gọi API model. Ngoài checker của pipeline, mọi đề phải khác đề trong
curriculum gốc và trong bộ đã duyệt của Member 2.

    python scripts/authoring/prepare_member1_pilot.py
    python scripts/authoring/prepare_member1_pilot.py --output artifacts/member1-review-01
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_member2_pilot import make_case, make_pack, review_material  # noqa: E402

from app.authoring_runs import RunStore, load_authoring_source, load_json  # noqa: E402
from app.content_authoring import check_draft, digest, review_template  # noqa: E402
from app.curriculum import CurriculumRegistry, PilotBank, load_curriculum  # noqa: E402
from app.final_answer import is_final_form  # noqa: E402
from app.member2_foundation import load_workboard  # noqa: E402

SOURCE = ROOT / "content/authoring/member1-original-pilot.v1.json"
MEMBER3_SOURCE = ROOT / "content/authoring/member3-original-pilot.v1.json"
OWNER = "Member 1"
AUTHOR = "AI-assisted authoring (Member 1)"


def rendered_pilot(source=SOURCE):
    spec = load_json(source)
    version, revision, specifications = spec["version"], spec["revision"], spec["packs"]
    assignment = next(item for item in load_workboard().assignments if item.owner == OWNER)
    assigned = set(assignment.concept_ids)
    pending = set(spec.get("pending_checker", {}))
    if not set(specifications).issubset(assigned) or set(specifications) & pending:
        raise ValueError("Packs must be Member 1 concepts and not marked as pending a checker")
    if set(specifications) | pending != assigned:
        raise ValueError("Every Member 1 concept must be either authored or listed as pending a checker")

    baseline_registry, baseline_bank = load_curriculum(revision="v2")
    _, member2_bank = load_authoring_source("member2-v2")
    registry_data = baseline_registry.model_dump(mode="json")
    registry_data["content_version"] = version
    for concept in registry_data["concepts"]:
        if concept["concept_id"] in specifications:
            concept["pilot"] = True
            concept["authoring_task_kinds"] = sorted({f["kind"] for f in specifications[concept["concept_id"]]["families"]})
    registry = CurriculumRegistry.model_validate(registry_data)
    seen = {digest(case.task.model_dump(mode="json")) for bank in (baseline_bank, member2_bank)
            for pack in bank.packs for case in [*pack.problems, *pack.examples]}
    # Member 3's source may not yet be materialized in a PilotBank.
    member3_source = load_json(MEMBER3_SOURCE)
    for concept_spec in member3_source["packs"].values():
        for family in concept_spec.get("families", []):
            seeds = [*family.get("problems", []), family.get("example", [])]
            for number, seed in enumerate(seeds, 1):
                if seed:
                    case, _ = make_case(seed, family["kind"], f"M3-DUP-CHECK-{number:02}")
                    seen.add(digest(case["task"]))

    reports, packs, artifacts = {}, [], {"registry-snapshot.json": registry.model_dump(mode="json")}
    for concept in registry.concepts:
        concept_id = concept.concept_id
        if concept_id not in specifications:
            continue
        specification = specifications[concept_id]
        request, pack, example_prompts = make_pack(concept, specification, version, revision,
                                                   lineage=revision, author=AUTHOR)
        checks = check_draft(pack, request, registry, baseline_bank)
        failures = [i.model_dump() for i in checks.issues if i.severity == "error" or i.code == "partial_concept_scope"]
        if failures:
            raise ValueError(f"{concept_id} authoring checks failed: {failures}")
        for item in [*pack.problems, *pack.examples]:
            if not is_final_form(item.task.kind, item.task.expression, item.reference_answer,
                                 getattr(item, 'prompt', '')):
                raise ValueError(f"Reference answer is not in final form: {item.case_id}")
            task = digest(item.task.model_dump(mode="json"))
            if task in seen:
                raise ValueError(f"Exact task duplicate: {item.case_id}")
            seen.add(task)
        worked = [family["worked"] for family in specification["families"]]
        prerequisites = sorted(
            edge.source_concept_id for edge in registry.edges
            if edge.target_concept_id == concept_id and edge.relation == "PREREQUISITE_OF"
        )
        metadata = {
            "concept_id": concept.concept_id,
            "title": concept.title,
            "primary_skill_id": concept.skills[0].skill_id,
            "strand": concept.strand,
            "objective": concept.objective,
            "grade_levels": concept.alignment.grade_levels,
            "prerequisites": prerequisites,
            "supported_forms": concept.supported_forms,
            "excluded_forms": concept.excluded_forms,
        }
        metadata_lines = [
            "## Metadata registry", "",
            f"- Concept: `{concept_id}` · {concept.title}",
            f"- Primary skill: `{concept.skills[0].skill_id}`",
            f"- Strand: `{concept.strand}`",
            f"- Objective: {concept.objective}",
            f"- Grade levels: {', '.join(map(str, concept.alignment.grade_levels))}",
            f"- Prerequisites: {', '.join(prerequisites) if prerequisites else 'Không có'}",
            f"- Supported forms: {', '.join(concept.supported_forms)}",
            f"- Excluded forms: {', '.join(concept.excluded_forms)}", "",
        ]
        review_doc = review_material(concept, pack, request, example_prompts, worked,
                                     checks, assignment.reviewer)
        review_doc += "\n" + "\n".join(metadata_lines)
        packs.append(pack)
        artifacts.update({f"{concept_id}/request.json": request.model_dump(mode="json"),
                          f"{concept_id}/draft.json": pack.model_dump(mode="json"),
                          f"{concept_id}/checks.json": {**checks.model_dump(mode="json"), "passed": True},
                          f"{concept_id}/example-prompts.json": example_prompts,
                          f"{concept_id}/review-template.json": review_template(pack),
                          f"{concept_id}/registry-metadata.json": metadata,
                          f"{concept_id}/review.md": review_doc})
        reports[concept_id] = {"problems": len(pack.problems), "examples": len(pack.examples),
                               "error_fixtures": len(pack.errors), "hint_levels": len(pack.hints),
                               "task_kinds": concept.authoring_task_kinds, "pack_sha256": checks.pack_sha256,
                               "review": pack.review.status}
    artifacts["draft-bank.json"] = PilotBank(schema_version="1.0.0", content_version=version,
                                             packs=packs).model_dump(mode="json")
    summary = {"content_version": version, "status": "drafts_ready_for_review", "owner": OWNER,
               "reviewer": assignment.reviewer, "member1_concepts": assignment.concept_ids,
               "pending_checker": spec.get("pending_checker", {}), "model_api_calls_for_this_batch": 0,
               "runtime_publication": False, "packs": reports,
               "source_sha256": {(source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else source.name):
                                 sha256(source.read_bytes()).hexdigest() for source in (SOURCE, MEMBER3_SOURCE)}}
    artifacts["README.md"] = "\n".join([
        "# Hồ sơ review concept Member 1", "",
        f"Phiên bản `{version}`. Người review theo phân công là {assignment.reviewer}.", "",
        "Mỗi mục có đề, đáp án, mẫu lỗi, hint, ba ví dụ có lời giải và checklist riêng. "
        "Các tệp trong thư mục này dùng cho review nội bộ.", "",
        *(f"- [{cid} · {next(c.title for c in registry.concepts if c.concept_id == cid)}]({cid}/review.md)"
          for cid in assignment.concept_ids if cid in reports), "",
        "Chưa soạn vì checker chưa hỗ trợ dạng bài:", "",
        *(f"- {cid}: {why}" for cid, why in spec.get("pending_checker", {}).items()), "",
    ])
    return artifacts, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Xuất hồ sơ review vào một thư mục mới trong artifacts/")
    args = parser.parse_args()
    artifacts, summary = rendered_pilot()
    if args.output:
        output = args.output.resolve()
        root = (ROOT / "artifacts").resolve()
        if output == root or not output.is_relative_to(root):
            parser.error("Pilot directory must be under artifacts/")
        output.mkdir(parents=True, exist_ok=False)
        hashes = {}
        for relative, value in artifacts.items():
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".md":
                with path.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(value)
                hashes[relative] = sha256(path.read_bytes()).hexdigest()
            else:
                hashes[relative] = RunStore.write(path, value)
        RunStore.write(output / "manifest.json", {**summary, "artifact_sha256": hashes})
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
