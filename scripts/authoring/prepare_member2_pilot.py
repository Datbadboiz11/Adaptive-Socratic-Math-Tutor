"""Check and optionally materialize Member 2's original, draft-only pilot packs."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.authoring_math import polynomial
from app.authoring_runs import RunStore, load_json
from app.content_authoring import (
    ContentReview, DraftRequest, GeneratedContent, apply_review, check_draft, digest, make_draft, review_template,
)
from app.curriculum import ConceptPack, CurriculumRegistry, PilotBank, load_curriculum
from app.member2_foundation import load_workboard


SOURCE = ROOT / "content/authoring/member2-original-pilot.v1.json"
REVIEW_SOURCE = ROOT / "content/authoring/member2-original-pilot.v2.json"
REPLACEMENTS = {"A02", "E02"}
REVISION = "M2-ORIG01"


def make_case(seed, kind, case_id):
    expression, answer, *display = seed
    variable = None
    if kind == "evaluate":
        expression, variable = expression.split(" @ ")
    reference_steps = [answer]
    if kind == "linear_equation":
        lhs, rhs = (polynomial(part.strip()) for part in expression.split("="))
        reduced = f"{lhs[1] - rhs[1]}*x={rhs[0] - lhs[0]}"
        if reduced != expression and reduced != answer:
            reference_steps.insert(0, reduced)
    return {
        "case_id": case_id, "task": {"kind": kind, "expression": expression, "variable_value": variable},
        "reference_answer": answer, "reference_steps": reference_steps,
    }, display[0] if display else expression


def make_pack(concept, specification, version, revision=REVISION, *, lineage=REVISION,
              author="Codex assisted authoring"):
    if len(concept.skills) != 1:
        raise ValueError("Choose a primary skill for every pilot family")
    concept_id = concept.concept_id
    prefix = f"D-{concept_id}-{revision}-"
    problems, examples, errors, families = [], [], [], []
    for index, family in enumerate(specification["families"], 1):
        family_id = f"FAM-{concept_id}-{revision}-{index}"
        # The revised pack shares lineage with the corresponding v1 family.
        source_group = f"GROUP-{concept_id}-{lineage}-{index}"
        families.append({"family_id": family_id, "source_group": source_group, "description": family["label"]})
        first_problem_id = f"{prefix}P-{2*index-1:02}"
        for difficulty, seed in zip(("introductory", "standard"), family["problems"], strict=True):
            case, display = make_case(seed, family["kind"], f"{prefix}P-{len(problems)+1:02}")
            prompt = family["prompt"].replace("{expression}", case["task"]["expression"]).replace("{display}", display)
            prompt = prompt.replace("{variable}", case["task"]["variable_value"] or "")
            problems.append({**case, "concept_id": concept_id, "primary_skill_id": concept.skills[0].skill_id,
                             "family_id": family_id, "source_group": source_group, "difficulty": difficulty,
                             "prompt": prompt, "split": "authoring_dev",
                             "origin": "Bài tự biên soạn cho pilot Chặng 2. Nguồn chương trình chỉ dùng để định phạm vi."})
        example, example_display = make_case(family["example"], family["kind"], f"{prefix}EX-{index:02}")
        example_prompt = family["prompt"].replace("{expression}", example["task"]["expression"])
        example_prompt = example_prompt.replace("{display}", example_display).replace(
            "{variable}", example["task"]["variable_value"] or "",
        )
        examples.append((example, example_prompt))
        errors.append({"error_id": f"{prefix}ERR-{index:02}", "problem_id": first_problem_id,
                       "response_steps": family.get("wrong_steps", [family["wrong"]]),
                       "first_error_step": family.get("first_error_step", 1),
                       "family": (f"{family['catalog_error_id']} · " if family.get("catalog_error_id") else "") + family["label"],
                       "hypothesis": family["hypothesis"], "diagnostic_question": family["question"],
                       "diagnosis_status": "suspected"})
    hints = [{"level": level, "text": text, "disclosure": disclosure}
             for level, (text, disclosure) in enumerate(zip(
                 specification["hints"], ("conceptual", "strategy", "scaffold"), strict=True,
             ), 1)]
    request = DraftRequest(concept_id=concept_id, revision=revision, author=author,
                           content_version=version, source_ids=[concept.alignment.source_id], families=families,
                           model="offline-original-pilot")
    content = GeneratedContent(explanation=specification["explanation"], problems=problems,
                               examples=[case for case, _ in examples], errors=errors, hints=hints)
    return request, make_draft(content, request), {case["case_id"]: display for case, display in examples}


def review_edition(base, assigned):
    revision = load_json(REVIEW_SOURCE)
    specifications = {cid: base["packs"][cid] for cid in assigned}
    if (revision["base_content_version"] != base["version"] or set(revision["worked_examples"]) != assigned
            or not set(revision["concept_edits"]).issubset(assigned)):
        raise ValueError("The review edition must be pinned to the full Member 2 workboard")
    for concept_id, edits in revision["concept_edits"].items():
        specification = specifications[concept_id]
        if not set(edits).issubset(specification):
            raise ValueError(f"{concept_id} contains an unknown pack field")
        for field in ("explanation", "hints"):
            if field in edits:
                specification[field] = edits[field]
        for number, changes in edits.get("families", {}).items():
            if number not in ("1", "2", "3"):
                raise ValueError(f"Unknown family in {concept_id}: {number}")
            family = specification["families"][int(number) - 1]
            if not set(changes).issubset(family):
                raise ValueError(f"{concept_id} contains an unknown family field")
            family.update(changes)
    return revision["version"], revision["revision"], specifications, revision["worked_examples"]


def review_material(concept, pack, request, example_prompts, worked, checks, reviewer):
    lines = [f"# {concept.concept_id} · {concept.title}", "",
             f"Bản {pack.content_version}. Người review theo phân công là {reviewer}. Trạng thái chờ review.", "",
             f"SHA-256 của pack `{checks.pack_sha256}`.", "",
             f"**Hành vi đo** {concept.skills[0].observable_behavior}", "",
             f"**Phạm vi** {', '.join(concept.supported_forms)}.", "",
             f"**Nguồn chương trình** `{concept.alignment.source_id}` · {concept.alignment.locator}", "",
             "## Giải thích và hint", "", pack.explanation, "",
             *(f"{hint.level}. {hint.text}" for hint in pack.hints), "",
             "## Bài và ví dụ theo họ", ""]
    for family, example, explanation in zip(request.families, pack.examples, worked, strict=True):
        if not explanation.strip():
            raise ValueError(f"Missing worked explanation for {example.case_id}")
        lines.extend([f"### {family.description}", ""])
        for problem in pack.problems:
            if problem.family_id == family.family_id:
                lines.extend([f"- `{problem.case_id}` {problem.prompt}",
                              f"  - Đáp án kiểm tra `{problem.reference_answer.strip()}`"])
        lines.extend(["", f"**Ví dụ** {example_prompts[example.case_id]}", "", explanation, "",
                      f"Dạng đáp án dùng trong checker `{example.reference_answer.strip()}`.", ""])
    lines.extend(["## Mẫu lỗi cần review", ""])
    for error in pack.errors:
        lines.extend([f"- `{error.problem_id}` · `{error.response_steps[0]}`", f"  - {error.hypothesis}",
                      f"  - {error.diagnostic_question}"])
    lines.extend(["", "## Ghi kết quả review", "",
                  "Dùng `review-template.json` để ghi người review, thời điểm, nhận xét và kết quả từng mục. "
                  "Hồ sơ này có đáp án và dùng trong buổi review nội bộ.", ""])
    return "\n".join(lines)


def rendered_pilot(edition="v1"):
    spec = load_json(SOURCE)
    version, specifications = spec["version"], spec["packs"]
    workboard = load_workboard()
    assignment = next(item for item in workboard.assignments if item.owner == "Member 2")
    assigned = set(assignment.concept_ids)
    if len(assigned) != 13 or not assigned.issubset(specifications):
        raise ValueError("Pilot must cover the 13 assigned Member 2 concepts")
    specifications = {cid: value for cid, value in specifications.items() if cid in assigned}

    revision, worked = REVISION, {}
    if edition == "v2":
        version, revision, specifications, worked = review_edition(spec, assigned)
    elif edition != "v1":
        raise ValueError("Unknown Member 2 pilot edition")

    baseline_registry, baseline_bank = load_curriculum(revision="v2")
    registry_data = baseline_registry.model_dump(mode="json")
    registry_data["content_version"] = version
    for concept in registry_data["concepts"]:
        concept_id = concept["concept_id"]
        concept["pilot"] = concept_id in specifications
        if concept["pilot"]:
            concept["authoring_task_kinds"] = sorted({f["kind"] for f in specifications[concept_id]["families"]})
    registry = CurriculumRegistry.model_validate(registry_data)
    legacy_tasks = [case.task.model_dump(mode="json") for pack in baseline_bank.packs
                    for case in [*pack.problems, *pack.examples]]
    seen = {digest(task) for task in legacy_tasks}
    reports, packs, artifacts = {}, [], {"registry-snapshot.json": registry.model_dump(mode="json")}
    for concept in registry.concepts:
        concept_id = concept.concept_id
        if concept_id not in specifications:
            continue
        request, pack, example_prompts = make_pack(concept, specifications[concept_id], version, revision)
        checks = check_draft(pack, request, registry, baseline_bank)
        failures = [i.model_dump() for i in checks.issues if i.severity == "error" or i.code == "partial_concept_scope"]
        if failures:
            raise ValueError(f"{concept_id} authoring checks failed: {failures}")
        for item in [*pack.problems, *pack.examples]:
            task = digest(item.task.model_dump(mode="json"))
            if task in seen:
                raise ValueError(f"Exact task duplicate: {item.case_id}")
            seen.add(task)
        packs.append(pack)
        artifacts.update({f"{concept_id}/request.json": request.model_dump(mode="json"),
                          f"{concept_id}/draft.json": pack.model_dump(mode="json"),
                          f"{concept_id}/checks.json": {**checks.model_dump(mode="json"), "passed": True},
                          f"{concept_id}/example-prompts.json": example_prompts,
                          f"{concept_id}/review-template.json": review_template(pack)})
        if worked:
            artifacts[f"{concept_id}/review.md"] = review_material(
                concept, pack, request, example_prompts, worked[concept_id], checks, assignment.reviewer,
            )
        reports[concept_id] = {"problems": len(pack.problems), "examples": len(pack.examples),
                               "error_fixtures": len(pack.errors), "hint_levels": len(pack.hints),
                               "task_kinds": concept.authoring_task_kinds, "pack_sha256": checks.pack_sha256,
                               "review": pack.review.status}
    bank = PilotBank(schema_version="1.0.0", content_version=version, packs=packs)
    artifacts["draft-bank.json"] = bank.model_dump(mode="json")
    summary = {"content_version": version, "status": "drafts_ready_for_review", "member2_concepts": sorted(assigned),
               "original_replacements": sorted(set(specifications) & REPLACEMENTS), "model_api_calls_for_this_batch": 0,
               "runtime_publication": False, "packs": reports}
    if worked:
        summary["reviewer"] = assignment.reviewer
        summary["source_sha256"] = {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
                                     for path in (SOURCE, REVIEW_SOURCE)}
        artifacts["README.md"] = "\n".join([
            "# Hồ sơ review 13 concept Member 2", "",
            f"Phiên bản `{version}`. Người review theo phân công là {assignment.reviewer}.", "",
            "Mỗi mục có đề, đáp án, mẫu lỗi, hint, ba ví dụ có lời giải và checklist riêng. "
            "Các tệp trong thư mục này dùng cho review nội bộ.", "",
            *(f"- [{cid} · {next(c.title for c in registry.concepts if c.concept_id == cid)}]({cid}/review.md)"
              for cid in assignment.concept_ids), "",
        ])
    return artifacts, summary


def record_review(batch, concept_id, review_file, artifacts, summary):
    if concept_id not in summary["packs"]:
        raise ValueError("Unknown pilot concept")
    manifest = load_json(batch / "manifest.json")
    for name in ("registry-snapshot.json", f"{concept_id}/request.json", f"{concept_id}/draft.json"):
        path = batch / name
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != manifest["artifact_sha256"][name] or json.loads(raw) != artifacts[name]:
            raise ValueError("Draft or source changed since the checked snapshot")
    material_path = f"{concept_id}/review.md"
    if material_path in artifacts:
        material = (batch / material_path).read_bytes()
        if sha256(material).hexdigest() != manifest["artifact_sha256"][material_path] or material.decode("utf-8") != artifacts[material_path]:
            raise ValueError("The annotated review material changed since the checked snapshot")
    registry = CurriculumRegistry.model_validate(artifacts["registry-snapshot.json"])
    request = DraftRequest.model_validate(artifacts[f"{concept_id}/request.json"])
    pack = ConceptPack.model_validate(artifacts[f"{concept_id}/draft.json"])
    _, bank = load_curriculum(revision="v2")
    review = ContentReview.model_validate(load_json(review_file))
    candidate = apply_review(pack, review, request, registry, bank)
    destination = (batch / "reviews" / concept_id / review.review_id).resolve()
    if not destination.is_relative_to(batch):
        raise ValueError("Invalid pilot review directory")
    destination.mkdir(parents=True, exist_ok=False)
    RunStore.write(destination / "review.json", review.model_dump(mode="json"))
    if material_path in artifacts:
        RunStore.write(destination / "review-source.json", {"content_version": pack.content_version,
                                                             "material_sha256": sha256(material).hexdigest()})
    if candidate is not None:
        RunStore.write(destination / "approved-pack.json", candidate.model_dump(mode="json"))
    return {"review": str(destination), "approved_candidate": candidate is not None, "runtime_publication": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("v1", "v2"), default="v1", help="v2 prepares the 13 Member 2 review packs")
    parser.add_argument("--output", type=Path, help="Materialize or review a pilot directory under artifacts/")
    parser.add_argument("--concept", help="Concept in the pilot when recording a review")
    parser.add_argument("--review-file", type=Path, help="Completed independent review of the checked draft")
    args = parser.parse_args()
    if bool(args.concept) != bool(args.review_file) or args.review_file and not args.output:
        parser.error("Review requires --concept, --review-file and --output pointing to the existing pilot")
    artifacts, summary = rendered_pilot(args.edition)
    if not args.output:
        print(json.dumps(summary, ensure_ascii=True, indent=2))
        return
    output = args.output.resolve()
    root = (ROOT / "artifacts").resolve()
    if output == root or not output.is_relative_to(root):
        parser.error("Pilot directory must be under artifacts/")
    if args.review_file:
        print(json.dumps(record_review(output, args.concept, args.review_file, artifacts, summary), ensure_ascii=True))
    else:
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
