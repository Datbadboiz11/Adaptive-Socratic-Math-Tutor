"""Publish only explicit teaching projections from versioned, approved source content."""
from dataclasses import dataclass
import json
from pathlib import Path

from app.curriculum import ConceptPack, CurriculumRegistry, PilotBank, load_curriculum
from app.kb_contracts import EmbeddingProfile, ExamplePublication, KBChunk, ChunkProvenance, KB_VERSION
from app.manage import digest
from app.member2_contracts import ContentSource

ROOT = Path(__file__).resolve().parents[2]


def load_source(source="oatutor-v2"):
    if source == "curriculum":
        registry, bank = load_curriculum()
        return registry, bank, "content/curriculum/pilot.v1.json"
    if source != "oatutor-v2":
        raise ValueError("Unknown versioned source")
    base = ROOT / "content/authoring/batches/a02-e02-oatutor.v2"
    registry = CurriculumRegistry.model_validate_json((base / "registry-snapshot.json").read_text(encoding="utf-8"))
    packs = [ConceptPack.model_validate_json((base / cid / "draft.json").read_text(encoding="utf-8")) for cid in ("A02", "E02")]
    bank = PilotBank(schema_version="1.0.0", content_version=registry.content_version, packs=packs)
    return registry, bank, "content/authoring/batches/a02-e02-oatutor.v2"


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
                    or chunk.content_version != chunk.provenance.pack_version
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
            metadata = {**common, "review": item.review}
            chunks.append(KBChunk(**metadata, content_id=example.case_id, kind="example", text=item.teaching_text,
                hint_level=3, disclosure="different_example", difficulty=item.difficulty, problem_id=example.case_id,
                source_group=item.source_group, family_id=item.family_id, lineage_ids=item.lineage_ids))
    return Projection(namespace, registry, registry_hash, digest(bank.model_dump(mode="json")), profile,
        tuple(sorted(chunks, key=lambda c: (c.content_id, c.content_version))), tuple(blocked), origin).validate()


def load_profile(path=None):
    path = path or ROOT / "content/kb/embedding-profile.v1.json"
    return EmbeddingProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))
