"""Stage 3 publication boundary and contracts. No network, DB, or real approvals."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "backend"))
sys.path.insert(0,str(ROOT / "tests"))
from app.embeddings import LocalEmbedder, checked_vector
from app.kb_contracts import ExamplePublication, KBRequest, KBScope
from app.kb_projection import load_example_publications, load_profile, load_source, project
from app.kb_tool import BoundTeachingContentTool
from app.manage import digest
from kb_support import approved_source, fake_profile, fixture_projection, request_for


def test_both_real_sources_are_draft_and_publish_zero_chunks():
    for source in ("curriculum","oatutor-v2"):
        registry,bank,origin = load_source(source)
        p = project(registry,bank,load_profile(),origin=origin)
        assert p.chunks == () and len(p.blocked) == len(bank.packs)
        assert all("pack_review" in b["reasons"] for b in p.blocked)


def test_approved_member2_source_publishes_all_13_packs_and_39_examples():
    registry,bank,origin = load_source("member2-v2")
    examples = load_example_publications("member2-v2")
    without_examples = project(registry,bank,load_profile(),origin=origin)
    projection = project(registry,bank,load_profile(),origin=origin,examples=examples)
    assert len(bank.packs)==13 and len(examples)==39
    assert len(without_examples.chunks)==52 and len(without_examples.blocked)==39
    assert len(projection.chunks)==91 and projection.blocked==()
    assert {chunk.concept_id for chunk in projection.chunks}=={pack.concept_id for pack in bank.packs}
    assert sum(chunk.kind=="example" for chunk in projection.chunks)==39
    assert all(example.pack_hash==next(chunk.provenance.pack_hash for chunk in projection.chunks
               if chunk.problem_id==example.case_id) for example in examples)
    serialized = json.dumps([chunk.model_dump(mode="json") for chunk in projection.chunks])
    assert all(field not in serialized for field in ("reference_answer","reference_steps","response_steps"))


@pytest.mark.parametrize("gate",["concept","alignment","pack"])
def test_three_review_gates_are_independent(gate):
    registry,bank = approved_source()
    if gate == "concept":
        next(c for c in registry.concepts if c.concept_id=="A02").review.status = "draft"
    elif gate == "alignment":
        concept = next(c for c in registry.concepts if c.concept_id=="A02")
        concept.review.status = "draft"  # Registry itself forbids approved concept with unapproved alignment.
        concept.alignment.status = "proposed"
    else:
        bank.packs[0].review.status = "machine_checked"
    p = project(registry,bank,fake_profile(),namespace="fixture-gates")
    assert all(c.concept_id != "A02" for c in p.chunks)


def test_projection_keeps_private_references_out_and_does_not_mutate_sources():
    registry,bank = approved_source()
    bank.packs[0].problems[0].reference_answer = "PRIVATE-REFERENCE-SENTINEL"
    before = digest(bank.model_dump(mode="json"))
    p = project(registry,bank,fake_profile(),namespace="fixture-projection")
    assert len(p.chunks) == 8
    serialized = json.dumps([c.model_dump(mode="json") for c in p.chunks])
    for forbidden in ("PRIVATE-REFERENCE-SENTINEL","reference_answer","reference_steps","response_steps"):
        assert forbidden not in serialized
    assert digest(bank.model_dump(mode="json")) == before
    assert all(c.difficulty is None and c.counts_as_assistance for c in p.chunks)
    assert all(c.kind != "example" for c in p.chunks)


def test_examples_require_explicit_review_metadata_and_correct_pack_hash():
    p = fixture_projection(examples=True)
    example = next(c for c in p.chunks if c.kind=="example")
    assert example.family_id and example.lineage_ids and example.problem_id
    assert set(example.for_generator()).isdisjoint({"provenance","review","content_hash","reference_steps","family_id"})
    registry,bank = approved_source()
    approval = ExamplePublication(case_id=bank.packs[0].examples[0].case_id,pack_hash="0"*64,family_id="OTHER",
        source_group="OTHER",lineage_ids=["OTHER"],difficulty="standard",teaching_text="Separate teaching text.",review=bank.packs[0].review)
    with pytest.raises(ValueError,match="revision"):
        project(registry,bank,fake_profile(),namespace="fixture-example",examples=[approval])


def test_fixture_embedding_cannot_be_published_to_runtime():
    registry,bank = approved_source()
    with pytest.raises(ValueError,match="Synthetic"):
        project(registry,bank,fake_profile(),namespace="runtime")


def test_scope_is_pair_based_and_tool_inputs_cannot_override_permissions():
    p = fixture_projection()
    request = request_for(p)
    malicious = request.model_dump(mode="json")
    malicious["query"]["target_skill_id"] = "SK-E02-SOLVE"
    with pytest.raises(ValueError):
        KBRequest.model_validate(malicious)
    class NeverRetrieve:
        def retrieve(self,*args):
            raise AssertionError("Unauthorized tool input reached retrieval")
    tool = BoundTeachingContentTool(request.scope,NeverRetrieve())
    for field in ("scope","allowed_hint_level","namespace","kb_snapshot_version"):
        with pytest.raises(ValueError):
            tool.invoke({**request.query.model_dump(mode="json"),field:3})
    assert "scope" not in tool.input_schema["properties"]


@pytest.mark.parametrize("vector,dimension",[([0,0,0],3),([1,2],3),([float("nan"),1],2),([float("inf")],1)])
def test_invalid_vectors_are_rejected(vector,dimension):
    with pytest.raises(ValueError):
        checked_vector(vector,dimension)


def test_local_model_is_lazy_and_bad_weights_are_rejected_before_inference():
    embedder = LocalEmbedder(load_profile(),ROOT / "artifacts/nonexistent-kb-model")
    assert embedder._model is None and embedder.embed_many([]) == []
    with pytest.raises(FileNotFoundError):
        embedder.embed_query("synthetic query")


def test_scope_requires_example_exclusions_and_direct_requires_version():
    request = request_for(fixture_projection())
    for field in ("excluded_family_ids","excluded_lineage_ids","excluded_source_groups"):
        with pytest.raises(ValueError):
            KBScope.model_validate({**request.scope.model_dump(mode="json"),field:[]})
    with pytest.raises(ValueError):
        KBRequest.model_validate({**request.model_dump(mode="json"),"method":"direct"})
