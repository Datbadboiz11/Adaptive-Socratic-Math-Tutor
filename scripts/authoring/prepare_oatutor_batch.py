"""Fetch, prepare, verify and independently review a bounded OATutor authoring pilot."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.content_authoring import ContentReview, DraftRequest, apply_review, digest
from app.authoring_reviews import (
    CurriculumReview, LabelsReview, apply_curriculum_review, apply_labels_review,
    curriculum_review_template, label_review_template,
)
from app.authoring_revisions import a07_fragment, check_stage2_scope, check_text_encoding
from app.curriculum import ConceptPack, CurriculumRegistry, PilotBank, load_curriculum, safe_chunks
from app.oatutor_import import (
    PROTOCOL, SOURCE_ID, fetch_snapshot, file_hash, prepare_packs, read_json,
    require, write_json,
)
from app.retrieval_dev import build_dev_set

SELECTION = ROOT / "content/authoring/selections/a02-e02-oatutor.v1.json"
DEV_PROPOSAL = ROOT / "research/retrieval/dev/a02-e02.v1/queries.proposed.json"
SOURCE_ROOT = ROOT / "content/sources/oatutor/08ef4819889e"
BATCH_ROOT = ROOT / "content/authoring/batches/a02-e02-oatutor.v1"
SNAPSHOT_ID = "DEV-A02-E02-M2-OAT01"
SELECTION_V2 = ROOT / "content/authoring/selections/a02-e02-oatutor.v2.json"
DEV_PROPOSAL_V2 = ROOT / "research/retrieval/dev/a02-e02.v2/queries.proposed.json"
BATCH_ROOT_V2 = ROOT / "content/authoring/batches/a02-e02-oatutor.v2"
PACK_FILES = {"request.json", "draft.json", "checks.json", "review-template.json", "provenance.json"}
DEV_FILES = {"corpus.json", "queries.json", "qrels.json", "manifest.json", "labels-review-template.json"}
FILES = {"selection.json", "dev-proposal.json", "config-snapshot.json", "registry-base.json", "registry-snapshot.json",
         "bank-snapshot.json", "source-decision.json", "summary.json"}
FILES |= {f"{cid}/{name}" for cid in ("A02", "E02") for name in PACK_FILES}
FILES |= {"retrieval-dev/" + name for name in DEV_FILES}
V2_FILES = FILES | {"A07-fragment.json", "curriculum-review-template.json", "revision-info.json"}


def contained(path, parent):
    path, parent = Path(path).resolve(), Path(parent).resolve()
    require(path.is_relative_to(parent) and path != parent, "Destination must stay inside " + str(parent))
    return path


def derived_files(selection, proposal, source_root, base, bank, configs):
    revision2 = selection.get("stage2_revision") == 2
    if revision2:
        check_text_encoding(selection)
        check_text_encoding(proposal)
    staged, prepared = prepare_packs(selection, source_root, base, bank, configs)
    dev = build_dev_set(proposal, prepared, staged, selection.get("snapshot_id", SNAPSHOT_ID))
    if revision2:
        check_stage2_scope(prepared, staged)
        dev["labels-review-template.json"] = label_review_template(dev)
    adapted = [p for f in prepared.values() for p in f["provenance.json"] if p["origin_kind"] == "oatutor_adapted"]
    blank = sorted({p["upstream_problem_id"] for p in adapted
                    if any(not n["license"] for n in p["upstream_license_fields"])})
    files = {"selection.json": selection, "dev-proposal.json": proposal, "config-snapshot.json": configs,
             "registry-base.json": base.model_dump(mode="json"), "registry-snapshot.json": staged.model_dump(mode="json"),
             "bank-snapshot.json": bank.model_dump(mode="json"),
             "source-decision.json": {
                 "decision": "proposed_for_human_review", "human_reviewer": None, "reviewed_at": None,
                 "source_id": SOURCE_ID, "upstream_commit": selection["upstream_commit"],
                 "role": "Supplemental exercises; Vietnamese curriculum source stays SRC-MATH-2018",
                 "license_basis": "Pinned repository README CC BY 4.0; retain all per-item notices",
                 "items_with_blank_license_fields": blank,
                 "rights_review": "pending", "curriculum_alignment_review": "pending",
                 "translation_review": "pending", "measurement_change_review": "pending",
                 "material_changes": ["A02 positive: multiple choice to written expansion",
                                      "A02 negative: coefficient/constant questions combined into full expansion; variables renamed",
                                      "Reference steps, examples, errors, explanation and hints drafted with AI assistance"],
                 "instruction": "Reviewer must check grade/objective/form, item notices, attribution and changes; "
                                "OATutor course names do not establish Vietnamese grade alignment.",
             },
             "summary.json": {
                 "protocol_version": PROTOCOL, "status": "ready_for_review_not_approved",
                 "problems": 12, "oatutor_adapted_problems": len(adapted), "ai_supplement_problems": 12 - len(adapted),
                 "examples": sum(len(f["draft.json"]["examples"]) for f in prepared.values()),
                 "error_fixtures": sum(len(f["draft.json"]["errors"]) for f in prepared.values()),
                 "hint_levels": 6, "model_api_calls": 0, "human_approved_packs": 0,
                 "query_count": dev["manifest.json"]["query_count"], "qrel_count": dev["manifest.json"]["judgment_count"],
                 "source_items_with_blank_license_fields": len(blank),
                 "runtime_publication": False, "canonical_registry_and_pilot_modified": False,
                 "target_240_progress": "12 proposed problems in this new batch; 228 further target slots unfilled. "
                                        "Existing pilot/replay copies must not be counted again.",
             }}
    for cid, records in prepared.items():
        files.update({cid + "/" + name: value for name, value in records.items()})
    files.update({"retrieval-dev/" + name: value for name, value in dev.items()})
    if revision2:
        require(contained(ROOT / selection["previous_batch"], ROOT / "content/authoring/batches") == BATCH_ROOT,
                "Stage 2 revision must refer to the original pilot")
        check_batch(BATCH_ROOT)
        previous = {name: read_json(BATCH_ROOT / name) for name in
                    ("A02/draft.json", "A02/provenance.json", "E02/draft.json", "dev-proposal.json")}
        files["A07-fragment.json"] = a07_fragment(previous, staged, selection)
        files["curriculum-review-template.json"] = curriculum_review_template(staged)
        old_tasks = {digest(p["task"]) for cid in ("A02", "E02") for p in previous[cid + "/draft.json"]["problems"]}
        new_tasks = {digest(p["task"]) for f in prepared.values() for p in f["draft.json"]["problems"]}
        files["summary.json"].update(
            target_240_progress="Twelve current pilot problems cover two already-piloted concepts; "
                                "canonical drafts and revisions require separate coverage/deduplication accounting.",
            new_tasks_relative_to_v1=len(new_tasks - old_tasks),
            reused_tasks_relative_to_v1=len(new_tasks.intersection(old_tasks)),
            a07_relocated_problems=2, a07_complete_pack=False)
        files["revision-info.json"] = {
            "stage2_revision": 2, "revision": selection["revision"], "supersedes": selection["previous_batch"],
            "snapshot_id": dev["manifest.json"]["snapshot_id"],
            "scope": "A02 forward distribution only; A07 reverse-distribution records relocated, not counted as new",
            "e02_change": "Explains why division by zero is undefined; DEV-E02-03 relabeled against this revision",
            "human_review": "pending", "runtime_publication": False,
        }
    require(set(files) == (V2_FILES if revision2 else FILES), "Unexpected batch artifact layout")
    return files, staged, prepared


def build_batch(source_root=SOURCE_ROOT, destination=BATCH_ROOT, *, edition="pilot-v1"):
    source_root = contained(source_root, ROOT / "content/sources")
    destination = contained(destination, ROOT / "content/authoring/batches")
    require(not destination.exists(), "Batch already exists; use a new version/path, never overwrite")
    require(edition in ("pilot-v1", "stage2-v2"), "Unknown edition")
    selection, proposal = (read_json(SELECTION), read_json(DEV_PROPOSAL)) if edition == "pilot-v1" else (
        read_json(SELECTION_V2), read_json(DEV_PROPOSAL_V2))
    registry, bank = load_curriculum()
    configs = {cid: read_json(ROOT / "content/authoring/configs" / (cid.lower() + ".v1.json")) for cid in ("A02", "E02")}
    files, _, _ = derived_files(selection, proposal, source_root, registry, bank, configs)
    destination.mkdir(parents=True, exist_ok=False)
    for name, value in files.items():
        write_json(destination / name, value)
    manifest = {
        "protocol_version": PROTOCOL, "created_at": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": source_root.relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": file_hash(source_root / "snapshot.json"),
        "base_registry_sha256": digest(registry.model_dump(mode="json")),
        "bank_sha256": digest(bank.model_dump(mode="json")),
        "files": {name: file_hash(destination / name) for name in sorted(files)},
        "review_status": "pending", "runtime_publication": False,
        "note": "Checksums bind this review batch, not a digital signature or human approval.",
    }
    if selection.get("stage2_revision") == 2:
        manifest.update(layout="stage2-v2", previous_batch_manifest_sha256=file_hash(BATCH_ROOT / "manifest.json"))
    write_json(destination / "manifest.json", manifest)
    return files["summary.json"]


def check_batch(destination=BATCH_ROOT):
    destination = contained(destination, ROOT / "content/authoring/batches")
    manifest = read_json(destination / "manifest.json")
    require(manifest["protocol_version"] == PROTOCOL and manifest["review_status"] == "pending"
            and manifest["runtime_publication"] is False, "Batch must remain an unapproved review snapshot")
    require(manifest.get("layout", "pilot-v1") in ("pilot-v1", "stage2-v2"), "Unknown batch layout")
    revision2 = manifest.get("layout") == "stage2-v2"
    require(set(manifest["files"]) == (V2_FILES if revision2 else FILES), "Incomplete or unexpected batch manifest")
    if revision2:
        require(file_hash(BATCH_ROOT / "manifest.json") == manifest["previous_batch_manifest_sha256"], "Previous batch manifest changed")
    for name, expected in manifest["files"].items():
        require(file_hash(destination / name) == expected, "Changed review artifact: " + name)
    source_root = contained(ROOT / manifest["source_snapshot"], ROOT / "content/sources")
    require(file_hash(source_root / "snapshot.json") == manifest["source_snapshot_sha256"], "Source manifest changed")
    base = CurriculumRegistry.model_validate(read_json(destination / "registry-base.json"))
    bank = PilotBank.model_validate(read_json(destination / "bank-snapshot.json"))
    require(digest(base.model_dump(mode="json")) == manifest["base_registry_sha256"]
            and digest(bank.model_dump(mode="json")) == manifest["bank_sha256"], "Changed base inputs")
    selection, proposal = read_json(destination / "selection.json"), read_json(destination / "dev-proposal.json")
    require((selection.get("stage2_revision") == 2) == revision2, "Selection/layout mismatch")
    expected, staged, prepared = derived_files(selection, proposal, source_root, base, bank,
                                              read_json(destination / "config-snapshot.json"))
    for name, value in expected.items():
        require(read_json(destination / name) == value, "Rebuilt artifact mismatch: " + name)
    for cid, files in prepared.items():
        bank_data = bank.model_dump(mode="json")
        bank_data["packs"] = [files["draft.json"] if p["concept_id"] == cid else p for p in bank_data["packs"]]
        replaced = PilotBank.model_validate(bank_data)
        require(not safe_chunks(staged, replaced, cid, level=3), "Draft crossed publication boundary")
    return expected["summary.json"]


def record_review(destination, concept_id, review_file):
    destination = contained(destination, ROOT / "content/authoring/batches")
    require(concept_id in ("A02", "E02"), "Review scope is A02/E02")
    check_batch(destination)
    review = ContentReview.model_validate(read_json(review_file))
    manifest = read_json(destination / "manifest.json")
    require(review.reviewed_at >= datetime.fromisoformat(manifest["created_at"]), "Review predates batch")
    pack = ConceptPack.model_validate(read_json(destination / concept_id / "draft.json"))
    request = DraftRequest.model_validate(read_json(destination / concept_id / "request.json"))
    registry = CurriculumRegistry.model_validate(read_json(destination / "registry-snapshot.json"))
    bank = PilotBank.model_validate(read_json(destination / "bank-snapshot.json"))
    approved = apply_review(pack, review, request, registry, bank)
    path = contained(destination / "reviews" / concept_id / review.review_id, destination)
    path.mkdir(parents=True, exist_ok=False)
    write_json(path / "review.json", review.model_dump(mode="json"))
    if approved is not None:
        write_json(path / "approved-pack.json", approved.model_dump(mode="json"))
    return {"review_path": str(path), "approved_candidate": approved is not None, "runtime_publication": False}


def record_extended_review(destination, review_file, kind):
    destination = contained(destination, ROOT / "content/authoring/batches")
    check_batch(destination)
    created_at = datetime.fromisoformat(read_json(destination / "manifest.json")["created_at"])
    authors = {read_json(destination / cid / "request.json")["author"] for cid in ("A02", "E02")}
    if kind == "labels":
        review = LabelsReview.model_validate(read_json(review_file))
        dev = {name: read_json(destination / "retrieval-dev" / name) for name in ("corpus.json", "queries.json", "qrels.json")}
        candidate = apply_labels_review(dev["corpus.json"], dev["queries.json"], dev["qrels.json"], review, authors, created_at)
    else:
        require(kind == "curriculum", "Unknown review type")
        review = CurriculumReview.model_validate(read_json(review_file))
        registry = CurriculumRegistry.model_validate(read_json(destination / "registry-snapshot.json"))
        authors.update(c.review.author for c in registry.concepts if c.concept_id in ("A02", "E02"))
        result = apply_curriculum_review(registry, review, authors, created_at)
        candidate = {"registry-candidate.json": result.model_dump(mode="json")} if result is not None else None
    path = contained(destination / "reviews" / kind / review.review_id, destination)
    require(not path.exists(), "Review ID already exists")
    path.mkdir(parents=True, exist_ok=False)
    write_json(path / "review.json", review.model_dump(mode="json"))
    if candidate is not None:
        for name, value in candidate.items():
            write_json(path / name, value)
    write_json(path / "receipt.json", {"kind": kind, "review_sha256": file_hash(path / "review.json"),
               "artifacts": {name: file_hash(path / name) for name in candidate or {}}, "runtime_publication": False})
    return {"review_path": str(path), "approved_candidate": candidate is not None, "runtime_publication": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="Download only pinned selected source files")
    fetch.add_argument("--destination", type=Path, default=SOURCE_ROOT)
    build = commands.add_parser("build", help="Create a fresh immutable review batch")
    build.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    build.add_argument("--destination", type=Path)
    build.add_argument("--edition", choices=["pilot-v1", "stage2-v2"], default="pilot-v1")
    check = commands.add_parser("check", help="Offline read-only source/math/provenance/dev checks")
    check.add_argument("--batch", type=Path, default=BATCH_ROOT)
    review = commands.add_parser("review", help="Record a real independent content review; no runtime publication")
    review.add_argument("--batch", type=Path, default=BATCH_ROOT)
    review.add_argument("--concept", choices=["A02", "E02"], required=True)
    review.add_argument("--review-file", type=Path, required=True)
    for name in ("labels-review", "curriculum-review"):
        extended = commands.add_parser(name, help="Record an actual independent review without publishing")
        extended.add_argument("--batch", type=Path, default=BATCH_ROOT_V2)
        extended.add_argument("--review-file", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "fetch":
        destination = contained(args.destination, ROOT / "content/sources")
        manifest = fetch_snapshot(read_json(SELECTION), destination)
        result = {"source_root": str(destination), "commit": manifest["commit"], "files": len(manifest["files"])}
    elif args.command == "build":
        destination = args.destination or (BATCH_ROOT_V2 if args.edition == "stage2-v2" else BATCH_ROOT)
        result = build_batch(args.source_root, destination, edition=args.edition)
    elif args.command == "check":
        result = {"checks_passed": True, **check_batch(args.batch)}
    elif args.command == "review":
        result = record_review(contained(args.batch, ROOT / "content/authoring/batches"), args.concept, args.review_file)
    else:
        result = record_extended_review(args.batch, args.review_file, "labels" if args.command == "labels-review" else "curriculum")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
