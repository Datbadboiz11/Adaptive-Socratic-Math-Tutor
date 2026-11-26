"""Load the reviewed A02/E02 replacement packs and their versioned registry."""
from hashlib import sha256
import json
from pathlib import Path

from app.curriculum import ConceptPack, CurriculumRegistry, PilotBank, load_curriculum
from app.manage import digest


SOURCE = "content/authoring/batches/a02-e02-original.v1"
TOPICS = {"TOPIC-A02": "A02", "TOPIC-E02": "E02"}
TASKS = {"A02": "polynomial", "E02": "linear_equation"}
ROOT = Path(__file__).resolve().parents[2]


def load_original_packs():
    path = ROOT / SOURCE
    manifest = json.loads((path / "manifest.json").read_bytes())
    if (manifest["revision"] != "M2-ORIG01" or manifest["review_status"] != "human_approved"
            or set(manifest["packs"]) != set(TASKS)):
        raise ValueError("Original pack approval manifest is incomplete")
    version = manifest["content_version"]
    packs = []
    for concept_id, task_kind in TASKS.items():
        entry = manifest["packs"][concept_id]
        prefix = f"{concept_id}/"
        files = {name: (path / (prefix + name)).read_bytes() for name in ("approved-pack.json", "review.json")}
        if {prefix + name: sha256(data).hexdigest() for name, data in files.items()} != entry["files_sha256"]:
            raise ValueError("Original pack or review checksum mismatch")
        pack = ConceptPack.model_validate_json(files["approved-pack.json"])
        review = json.loads(files["review.json"])
        if (digest(pack.model_dump(mode="json")) != entry["approved_pack_sha256"]
                or review["decision"] != "approved" or review["pack_sha256"] != entry["draft_sha256"]
                or pack.review.status != "human_approved" or pack.review.human_reviewer != review["reviewer"]
                or pack.concept_id != concept_id or pack.content_version != version
                or any(problem.task.kind != task_kind for problem in pack.problems)):
            raise ValueError("Original pack is outside its approved release scope")
        packs.append(pack)

    registry, _ = load_curriculum(revision="v2")
    data = registry.model_dump(mode="json")
    data["content_version"] = version
    for concept in data["concepts"]:
        concept["pilot"] = concept["concept_id"] in TASKS
    registry = CurriculumRegistry.model_validate(data)
    return registry, PilotBank(schema_version="1.0.0", content_version=version, packs=packs)
