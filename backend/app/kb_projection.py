"""Publish only explicit teaching projections from versioned, approved source content."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from pydantic import TypeAdapter

from app.curriculum import CURRENT_CURRICULUM_REVISION, ConceptPack, CurriculumRegistry, PilotBank, load_curriculum
from app.kb_contracts import EmbeddingProfile, ExamplePublication, KBChunk, ChunkProvenance, KB_VERSION
from app.manage import digest
from app.member2_contracts import ContentSource

ROOT = Path(__file__).resolve().parents[2]
MEMBER2_SOURCE = ROOT / "content/authoring/batches/member2-original.v2"
MEMBER2_PUBLICATION = ROOT / "content/kb/member2-v2"


def _file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _verified_member2_source():
    manifest = json.loads((MEMBER2_SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("review_status") != "human_approved"
            or manifest.get("content_version") != "0.4.0-member2-review"
            or manifest.get("basis") != "user_confirmed_approval"):
        raise ValueError("Member 2 source does not carry the approved review record")
    if set(manifest["files_sha256"]) != {"registry-snapshot.json", "approved-bank.json"}:
        raise ValueError("Member 2 source manifest must pin both approved source files")
    for name, expected in manifest["files_sha256"].items():
        path = MEMBER2_SOURCE / name
        if not path.is_file() or _file_hash(path) != expected:
            raise ValueError("Member 2 approved source hash mismatch: " + name)
    for name, expected in manifest["source_sha256"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or _file_hash(path) != expected:
            raise ValueError("Member 2 reviewed authoring source hash mismatch: " + name)
    registry = CurriculumRegistry.model_validate_json(
        (MEMBER2_SOURCE / "registry-snapshot.json").read_text(encoding="utf-8"))
    bank = PilotBank.model_validate_json(
        (MEMBER2_SOURCE / "approved-bank.json").read_text(encoding="utf-8"))
    if registry.content_version != bank.content_version or len(bank.packs) != 13:
        raise ValueError("Member 2 source must contain the approved 13-pack revision")
    if any(pack.review.status != "human_approved" for pack in bank.packs):
        raise ValueError("Member 2 source contains an unapproved pack")
    if set(manifest["packs"]) != {pack.concept_id for pack in bank.packs} or any(
            manifest["packs"][pack.concept_id]["approved_pack_sha256"] != digest(pack.model_dump(mode="json"))
            for pack in bank.packs):
        raise ValueError("Member 2 packs do not match their approval hashes")
    return registry, bank


def load_source(source="oatutor-v2"):
    if source == "member2-v2":
        registry, bank = _verified_member2_source()
        return registry, bank, "content/authoring/batches/member2-original.v2"
    if source == "original-a02-e02":
        from app.original_packs import SOURCE, load_original_packs
        registry, bank = load_original_packs()
        return registry, bank, SOURCE
    if source == "curriculum":
        revision = CURRENT_CURRICULUM_REVISION
        registry, bank = load_curriculum(revision=revision)
        return registry, bank, f"content/curriculum/pilot.{revision}.json"
    if source != "oatutor-v2":
        raise ValueError("Unknown versioned source")
    base = ROOT / "content/authoring/batches/a02-e02-oatutor.v2"
    registry = CurriculumRegistry.model_validate_json((base / "registry-snapshot.json").read_text(encoding="utf-8"))
    packs = [ConceptPack.model_validate_json((base / cid / "draft.json").read_text(encoding="utf-8")) for cid in ("A02", "E02")]
    bank = PilotBank(schema_version="1.0.0", content_version=registry.content_version, packs=packs)
    return registry, bank, "content/authoring/batches/a02-e02-oatutor.v2"


def load_example_publications(source):
    """Load an explicit, hash-pinned publication set; draft sources have none."""
    if source != "member2-v2":
        return []
    manifest_path = MEMBER2_PUBLICATION / "manifest.json"
    examples_path = MEMBER2_PUBLICATION / "example-publications.json"
    if not manifest_path.is_file() or not examples_path.is_file():
        raise ValueError("Member 2 example publication assets are missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_manifest = MEMBER2_SOURCE / "manifest.json"
    expected = {
        "content/authoring/batches/member2-original.v2/manifest.json": _file_hash(source_manifest),
        "content/authoring/batches/member2-original.v2/approved-bank.json": _file_hash(MEMBER2_SOURCE / "approved-bank.json"),
        "content/authoring/batches/member2-original.v2/registry-snapshot.json": _file_hash(MEMBER2_SOURCE / "registry-snapshot.json"),
        "content/kb/member2-v2/example-publications.json": _file_hash(examples_path),
    }
    source_record = json.loads(source_manifest.read_text(encoding="utf-8"))
    expected.update(source_record["source_sha256"])
    if (manifest.get("source_file_sha256") != expected
            or manifest.get("content_version") != "0.4.0-member2-review"
            or manifest.get("concept_count") != 13
            or manifest.get("example_count") != 39):
        raise ValueError("Member 2 publication manifest is incomplete or stale")
    publications = TypeAdapter(list[ExamplePublication]).validate_json(
        examples_path.read_text(encoding="utf-8"))
    if len(publications) != 39 or any(item.review.status != "human_approved" for item in publications):
        raise ValueError("All 39 example publications require approved provenance")
    return publications


@dataclass(frozen=True)
class Projection:
    namespace: str
    registry: CurriculumRegistry
    registry_hash: str
    bank_hash: str
    profile: EmbeddingProfile
    chunks: tuple[KBChunk, ...]
    blocked: tuple[dict, ...]
    origin: str

    @property
    def manifest(self):
        return {"version": KB_VERSION, "namespace": self.namespace, "synthetic_fixture": self.namespace != "runtime",
                "registry_version": self.registry.content_version, "registry_hash": self.registry_hash,
                "bank_hash": self.bank_hash, "profile_id": self.profile.profile_id, "origin": self.origin,
                "chunks": [{"content_id": c.content_id, "content_version": c.content_version,
                            "content_hash": c.content_hash, "text_hash": c.text_hash} for c in self.chunks]}

    @property
    def snapshot_id(self):
        return "KB-" + digest(self.manifest)

    def validate(self):
        # Detect in-memory mutation as well as malformed hand-built projections.
        rebuilt = CurriculumRegistry.model_validate(self.registry.model_dump(mode="json"))
        if digest(rebuilt.model_dump(mode="json")) != self.registry_hash:
            raise ValueError("Registry changed after projection")
        if self.namespace == "runtime" and self.profile.provider == "synthetic_fixture":
            raise ValueError("Synthetic embeddings cannot be published to runtime")
        from pydantic import TypeAdapter
        from app.kb_contracts import Namespace
        TypeAdapter(Namespace).validate_python(self.namespace)
        keys = [(c.content_id, c.content_version) for c in self.chunks]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate projected chunk/version")
        concepts = {c.concept_id: c for c in rebuilt.concepts}
        for chunk in self.chunks:
            KBChunk.model_validate(chunk.model_dump(mode="json"))
            concept = concepts[chunk.concept_id]
            if (chunk.provenance.registry_hash != self.registry_hash
                    or (chunk.kind != "example" and chunk.content_version != chunk.provenance.pack_version)
                    or concept.review.status != "human_approved" or concept.alignment.status != "human_approved"
                    or not set(chunk.skill_ids).issubset({s.skill_id for s in concept.skills})
                    or set(chunk.grade_levels) != set(concept.alignment.grade_levels)):
                raise ValueError("Chunk provenance or registry permission mismatch")
        return self


def project(registry, bank, profile, *, namespace="runtime", origin="versioned source", examples=()):
    registry = CurriculumRegistry.model_validate(registry.model_dump(mode="json"))
    bank = PilotBank.model_validate(bank.model_dump(mode="json"))
    profile = EmbeddingProfile.model_validate(profile.model_dump(mode="json"))
    if registry.content_version != bank.content_version:
        raise ValueError("Registry/bank versions disagree")
    registry_hash = digest(registry.model_dump(mode="json"))
    concepts = {c.concept_id: c for c in registry.concepts}
    publications = {}
    for item in examples:
        item = ExamplePublication.model_validate(item.model_dump(mode="json"))
        if item.case_id in publications:
            raise ValueError("Duplicate example publication")
        publications[item.case_id] = item
    known_examples = {e.case_id for p in bank.packs for e in p.examples}
    if set(publications).difference(known_examples):
        raise ValueError("Example publication references an unknown case")
    chunks, blocked = [], []
    for pack in bank.packs:
        concept = concepts.get(pack.concept_id)
        if concept is None:
            raise ValueError("Pack references unknown concept")
        skills = {s.skill_id for s in concept.skills}
        if any(p.primary_skill_id not in skills for p in pack.problems):
            raise ValueError("Pack references an invalid concept/skill pair")
        if any(item.task.kind not in concept.authoring_task_kinds for item in [*pack.problems, *pack.examples]):
            raise ValueError("Pack task kind exceeds concept scope")
        reasons = [name for name, ok in (("concept_review", concept.review.status == "human_approved"),
            ("alignment_review", concept.alignment.status == "human_approved"), ("pack_review", pack.review.status == "human_approved")) if not ok]
        if reasons:
            blocked.append({"concept_id": pack.concept_id, "reasons": reasons})
            continue
        pack_hash = digest(pack.model_dump(mode="json"))
        provenance = ChunkProvenance(registry_hash=registry_hash, pack_hash=pack_hash, pack_version=pack.content_version,
            origin=origin, alignment_source_id=concept.alignment.source_id, alignment_locator=concept.alignment.locator)
        source = ContentSource(source_id="PACK-" + pack.concept_id, title=pack.review.source, locator=origin + "#" + pack.concept_id)
        common = dict(content_version=pack.content_version, concept_id=pack.concept_id,
            skill_ids=sorted(skills), grade_levels=concept.alignment.grade_levels, review=pack.review, source=source, provenance=provenance)
        chunks.append(KBChunk(**common, content_id=pack.concept_id + "-explanation", kind="explanation",
                              text=pack.explanation, hint_level=0, disclosure="conceptual"))
        for hint in pack.hints:
            chunks.append(KBChunk(**common, content_id=f"{pack.concept_id}-hint-{hint.level}", kind="hint",
                                  text=hint.text, hint_level=hint.level, disclosure=hint.disclosure))
        for example in pack.examples:
            item = publications.get(example.case_id)
            if not item or item.review.status != "human_approved":
                blocked.append({"case_id": example.case_id, "reasons": ["missing_reviewed_example_metadata"]})
                continue
            if item.pack_hash != pack_hash:
                raise ValueError("Example approval belongs to a different pack revision")
            metadata = {**common, "review": item.review,
                        "content_version": item.content_version or pack.content_version}
            chunks.append(KBChunk(**metadata, content_id=example.case_id, kind="example", text=item.teaching_text,
                hint_level=3, disclosure="different_example", difficulty=item.difficulty, problem_id=example.case_id,
                source_group=item.source_group, family_id=item.family_id, lineage_ids=item.lineage_ids))
    return Projection(namespace, registry, registry_hash, digest(bank.model_dump(mode="json")), profile,
        tuple(sorted(chunks, key=lambda c: (c.content_id, c.content_version))), tuple(blocked), origin).validate()


def load_profile(path=None):
    path = path or ROOT / "content/kb/embedding-profile.v1.json"
    return EmbeddingProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))
