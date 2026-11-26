"""Synthetic approval fixtures in memory only. Never write reviews to source content."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

from app.curriculum import CurriculumRegistry, PilotBank
from app.embeddings import checked_vector
from app.kb_contracts import EmbeddingProfile, ExamplePublication, KBRequest, KBScope
from app.kb_projection import load_source, project
from app.manage import digest
from app.member2_contracts import RetrievalQuery


def approved_source(version="0.1.0"):
    registry,bank,_ = load_source()
    rd,bd = registry.model_dump(mode="json"),bank.model_dump(mode="json")
    review = {"status":"human_approved","author":"Synthetic test fixture",
              "source":"Synthetic approval test only; no human attestation",
              "human_reviewer":"SYNTHETIC-NOT-A-REAL-REVIEWER","reviewed_at":"2026-11-18T00:00:00Z"}
    rd["content_version"] = bd["content_version"] = version
    for concept in rd["concepts"]:
        if concept["concept_id"] in ("A02","E02"):
            concept["review"] = deepcopy(review)
            concept["alignment"].update(status="human_approved",reviewer="SYNTHETIC-ALIGNMENT-FIXTURE")
    for pack in bd["packs"]:
        pack["content_version"] = version
        pack["review"] = deepcopy(review)
    return CurriculumRegistry.model_validate(rd),PilotBank.model_validate(bd)


def fake_profile(dimension=3, revision="fixture-v1"):
    return EmbeddingProfile(provider="synthetic_fixture",model_name="test-only-hash-embedding",revision=revision,dimension=dimension)


class FakeEmbedder:
    def __init__(self,profile=None):
        self.profile = profile or fake_profile()
        self.calls = 0
    def embed_many(self,texts):
        self.calls += len(texts)
        return [checked_vector([1 + (ord(text[i % len(text)]) % 13) for i in range(self.profile.dimension)],
                               self.profile.dimension) for text in texts]
    def embed_query(self,text):
        return self.embed_many([text])[0]


def fixture_projection(namespace=None,profile=None,version="0.1.0",examples=False):
    registry,bank = approved_source(version)
    approvals = []
    if examples:
        pack = bank.packs[0]
        approvals = [ExamplePublication(case_id=pack.examples[0].case_id,pack_hash=digest(pack.model_dump(mode="json")),
            family_id="SYNTHETIC-OTHER-FAMILY",source_group="SYNTHETIC-OTHER-SOURCE",lineage_ids=["SYNTHETIC-OTHER-LINEAGE"],
            difficulty="standard",teaching_text="Một ví dụ riêng: hãy xác định từng hạng tử trong một biểu thức khác.",review=pack.review)]
    return project(registry,bank,profile or fake_profile(),namespace=namespace or "fixture-"+uuid4().hex,
                   origin="synthetic approval fixture over copied draft teaching text",examples=approvals)


def request_for(projection,method="semantic",purpose="hint",level=3,**scope_changes):
    data = dict(namespace=projection.namespace,session_id=uuid4(),opportunity_id=uuid4(),
        allowed_targets=[{"concept_id":"A02","skill_id":"SK-A02-DISTRIBUTE"}],allowed_hint_level=level,
        kb_snapshot_version=projection.snapshot_id,active_problem_id="ACTIVE-PROBLEM",
        excluded_source_groups=["ACTIVE-SOURCE"],excluded_family_ids=["ACTIVE-FAMILY"],
        excluded_lineage_ids=["ACTIVE-LINEAGE"],grade_levels=[7,8],difficulty="standard")
    data.update(scope_changes)
    return KBRequest(request_id=uuid4(),query=RetrievalQuery(query="Nhân số ngoài ngoặc với từng hạng tử như thế nào?",
        concept_id="A02",target_skill_id="SK-A02-DISTRIBUTE",purpose=purpose,top_k=3),scope=KBScope.model_validate(data),
        method=method,direct_ref={"content_id":"A02-hint-1","content_version":projection.registry.content_version} if method=="direct" else None)
