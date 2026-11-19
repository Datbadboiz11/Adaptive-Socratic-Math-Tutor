"""Actual PostgreSQL/pgvector acceptance. Synthetic approvals stay in isolated test schemas."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "backend"))
sys.path.insert(0,str(ROOT / "tests"))
from app.db import connect
from app.kb_contracts import KBRequest
from app.kb_projection import load_profile, load_source, project
from app.kb_sync import active_snapshot, activate_snapshot, KBConflict, plan_sync, sync_projection, withdraw_pack
from app import kb_sync
from app.manage import migrate
from app.retrieval import KBRetriever
from kb_support import FakeEmbedder, approved_source, fake_profile, fixture_projection, request_for

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_DB_TESTS"),reason="Real PostgreSQL/pgvector requires RUN_DB_TESTS=1")


@pytest.fixture(scope="module",autouse=True)
def isolated_schema():
    name = "test_kb_" + uuid4().hex
    previous = os.environ.get("PGOPTIONS")
    with connect() as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    os.environ["PGOPTIONS"] = "-c search_path=" + name
    try:
        with connect() as c:
            migrate(c)
        yield
    finally:
        if previous is None:
            os.environ.pop("PGOPTIONS",None)
        else:
            os.environ["PGOPTIONS"] = previous
        assert name.startswith("test_kb_") and len(name)==40
        with connect() as c:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def counts(namespace):
    with connect() as c:
        return {table:c.execute(sql.SQL("SELECT count(*) AS n FROM {} WHERE namespace=%s").format(sql.Identifier(table)),(namespace,)).fetchone()["n"]
                for table in ("kb_registry_versions","kb_chunks","kb_snapshots","kb_snapshot_members","kb_sync_runs")}


def test_dry_run_is_read_only_and_sync_twice_reuses_embeddings():
    p = fixture_projection()
    embedder = FakeEmbedder(p.profile)
    before = counts(p.namespace)
    _,plan = plan_sync(p)
    assert plan["new_chunk_versions"] == plan["new_embeddings"] == 8
    assert counts(p.namespace) == before and embedder.calls == 0
    first = sync_projection(p,embedder,activate=True)
    again = sync_projection(p,embedder,activate=True)
    assert first["inserted_chunks"]==8 and again["inserted_chunks"]==again["computed_embeddings"]==0
    assert embedder.calls==8 and counts(p.namespace)["kb_snapshots"]==1
    with connect() as c:
        assert active_snapshot(c,p.namespace)==p.snapshot_id


def test_real_drafts_write_registry_but_no_chunks_or_embeddings():
    registry,bank,origin = load_source()
    p = project(registry,bank,load_profile(),namespace="fixture-real-draft-"+uuid4().hex[:8],origin=origin)
    class NeverEmbed:
        profile=p.profile
        def embed_many(self,texts):
            raise AssertionError("Drafts must not reach embedding")
    result = sync_projection(p,NeverEmbed(),activate=True)
    assert result["chunks"]==result["computed_embeddings"]==0 and result["concepts"]==40
    response = KBRetriever().retrieve(request_for(p,method="metadata"))
    assert response.chunks==[] and response.fallback_reason=="no_eligible_content"


@pytest.mark.parametrize("method",["direct","metadata","semantic"])
def test_three_methods_return_only_eligible_traced_chunks(method):
    p = fixture_projection()
    embedder = FakeEmbedder(p.profile)
    sync_projection(p,embedder)
    before = embedder.calls
    request = request_for(p,method=method,level=1)
    result = KBRetriever(embedder).retrieve(request)
    assert result.fallback_reason is None and [c.content_id for c in result.chunks]==["A02-hint-1"]
    assert embedder.calls == before+(1 if method=="semantic" else 0)
    assert result.snapshot_manifest_hash and result.embedding_version==p.profile.profile_id
    with connect() as c:
        row = c.execute("SELECT * FROM kb_retrieval_traces WHERE retrieval_id=%s",(result.retrieval_id,)).fetchone()
        assert row["request_id"]==request.request_id and len(row["selected_refs"])==1
        assert "text" not in row["selected_refs"][0] and "query" not in row


@pytest.mark.parametrize("change",["level","grade","version","concept_skill","source","family","lineage","difficulty"])
def test_filters_and_independent_example_exclusions(change):
    p = fixture_projection(examples=True)
    embedder = FakeEmbedder(p.profile)
    sync_projection(p,embedder)
    example = next(ch for ch in p.chunks if ch.kind=="example")
    request = request_for(p,method="metadata",purpose="example")
    data = request.model_dump(mode="json")
    if change=="level": data["scope"]["allowed_hint_level"]=2
    elif change=="grade": data["scope"]["grade_levels"]=[12]
    elif change=="version":
        data["method"]="direct"
        data["direct_ref"]={"content_id":example.content_id,"content_version":"99.0.0"}
    elif change=="concept_skill":
        data["query"]["concept_id"]="E02"
        data["query"]["target_skill_id"]="SK-E02-SOLVE"
        data["scope"]["allowed_targets"]=[{"concept_id":"E02","skill_id":"SK-E02-SOLVE"}]
    elif change=="source": data["scope"]["excluded_source_groups"]=[example.source_group]
    elif change=="family": data["scope"]["excluded_family_ids"]=[example.family_id]
    elif change=="lineage": data["scope"]["excluded_lineage_ids"]=example.lineage_ids
    elif change=="difficulty": data["scope"]["difficulty"]="introductory"
    result = KBRetriever(embedder).retrieve(KBRequest.model_validate(data))
    assert result.chunks==[] and result.fallback_reason=="no_eligible_content"


def test_matching_independent_example_is_available_but_active_problem_is_blocked():
    p = fixture_projection(examples=True)
    embedder = FakeEmbedder(p.profile)
    sync_projection(p,embedder)
    request = request_for(p,method="metadata",purpose="example")
    result = KBRetriever().retrieve(request)
    assert len(result.chunks)==1 and result.chunks[0].kind=="example"
    excluded = request.model_dump(mode="json")
    excluded["scope"]["active_problem_id"] = result.chunks[0].problem_id
    assert KBRetriever().retrieve(KBRequest.model_validate(excluded)).chunks==[]


def test_same_version_cannot_silently_change_text_or_registry():
    p = fixture_projection()
    sync_projection(p,FakeEmbedder(p.profile))
    changed = replace(p,chunks=(p.chunks[0].model_copy(update={"text":"Changed approved text"}),*p.chunks[1:]))
    with pytest.raises(KBConflict,match="Chunk version"):
        plan_sync(changed)
    registry,bank = approved_source()
    registry.concepts[0].title += " changed"
    with pytest.raises(KBConflict,match="Registry version"):
        plan_sync(project(registry,bank,p.profile,namespace=p.namespace,origin=p.origin))


def test_embedding_failure_keeps_previous_active_snapshot_and_records_failure():
    p = fixture_projection()
    sync_projection(p,FakeEmbedder(p.profile),activate=True)
    newer = fixture_projection(namespace=p.namespace,version="0.2.0")
    newer = replace(newer,chunks=(newer.chunks[0].model_copy(update={"text":"New teaching text requires embedding"}),*newer.chunks[1:]))
    class Broken(FakeEmbedder):
        def embed_many(self,texts):
            raise TimeoutError("synthetic inference failure")
    with pytest.raises(TimeoutError):
        sync_projection(newer,Broken(newer.profile),activate=True)
    with connect() as c:
        assert active_snapshot(c,p.namespace)==p.snapshot_id
        assert not c.execute("SELECT 1 FROM kb_snapshots WHERE namespace=%s AND snapshot_id=%s",(p.namespace,newer.snapshot_id)).fetchone()
        assert c.execute("SELECT status FROM kb_sync_runs WHERE namespace=%s ORDER BY started_at DESC LIMIT 1",(p.namespace,)).fetchone()["status"]=="failed"


def test_publish_failure_rolls_back_every_member_and_keeps_previous_snapshot(monkeypatch):
    p = fixture_projection()
    sync_projection(p,FakeEmbedder(p.profile),activate=True)
    newer = fixture_projection(namespace=p.namespace,version="0.2.0")
    before = counts(p.namespace)
    def interrupted(*args):
        raise RuntimeError("synthetic interrupted publish")
    monkeypatch.setattr(kb_sync,"assert_complete",interrupted)
    with pytest.raises(RuntimeError):
        sync_projection(newer,FakeEmbedder(newer.profile),activate=True)
    after = counts(p.namespace)
    assert all(after[table]==before[table] for table in before if table!="kb_sync_runs")
    with connect() as c:
        assert active_snapshot(c,p.namespace)==p.snapshot_id


def test_model_and_dimension_change_use_separate_embeddings_and_do_not_mix():
    p = fixture_projection()
    sync_projection(p,FakeEmbedder(p.profile),activate=True)
    newer = replace(p,profile=fake_profile(4,"fixture-v2"))
    sync_projection(newer,FakeEmbedder(newer.profile),activate=True)
    old_provider = KBRetriever(FakeEmbedder(p.profile))
    assert old_provider.retrieve(request_for(newer)).fallback_reason=="retrieval_unavailable"
    result = KBRetriever(FakeEmbedder(newer.profile)).retrieve(request_for(newer))
    assert result.chunks and result.embedding_version==newer.profile.profile_id
    assert old_provider.retrieve(request_for(p)).chunks  # Historical snapshot still uses its own model.


def test_withdrawal_blocks_historical_snapshot_and_new_sync_omits_it():
    p = fixture_projection()
    embedder = FakeEmbedder(p.profile)
    sync_projection(p,embedder,activate=True)
    withdraw_pack(p.namespace,"A02","0.1.0","synthetic revocation","test actor")
    result = KBRetriever(embedder).retrieve(request_for(p))
    assert result.chunks==[] and result.fallback_reason=="no_eligible_content"
    with pytest.raises(KBConflict,match="withdrawn"):
        activate_snapshot(p.namespace,p.snapshot_id)
    effective,plan = plan_sync(p)
    assert len(effective.chunks)==4 and all(ch.concept_id=="E02" for ch in effective.chunks)
    assert effective.snapshot_id != p.snapshot_id
    sync_projection(p,embedder,activate=True)
    with connect() as c:
        assert active_snapshot(c,p.namespace)==effective.snapshot_id


def test_concurrent_idempotent_sync_produces_one_complete_snapshot():
    p = fixture_projection()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(sync_projection,p,FakeEmbedder(p.profile),activate=True) for _ in range(2)]
        results = [f.result(timeout=20) for f in futures]
    assert sum(r["inserted_chunks"] for r in results)==8
    assert counts(p.namespace)["kb_snapshots"]==1


def test_no_snapshot_or_failed_provider_falls_back_without_math_or_learner_writes():
    p = fixture_projection()
    request = request_for(p)
    assert KBRetriever().retrieve(request).fallback_reason=="snapshot_unavailable"
    sync_projection(p,FakeEmbedder(p.profile))
    assert KBRetriever().retrieve(request).fallback_reason=="retrieval_unavailable"
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM observations").fetchone()["n"]==0
        assert c.execute("SELECT count(*) AS n FROM knowledge_states").fetchone()["n"]==0


def test_withdrawal_during_inference_cannot_publish_a_stale_approval():
    p = fixture_projection(profile=fake_profile(revision="withdraw-during-inference"))
    class Revoking(FakeEmbedder):
        def embed_many(self,texts):
            withdraw_pack(p.namespace,"A02","0.1.0","withdrawn while embedding","synthetic test")
            return super().embed_many(texts)
    with pytest.raises(KBConflict,match="withdrawn"):
        sync_projection(p,Revoking(p.profile),activate=True)
    assert counts(p.namespace)["kb_snapshots"]==0 and counts(p.namespace)["kb_chunks"]==0


def test_stale_activation_cannot_overwrite_a_newer_publisher():
    p = fixture_projection(profile=fake_profile(revision="race-original-model"))
    newer = replace(p,profile=fake_profile(4,"concurrent-model-v2"))
    class Racing(FakeEmbedder):
        def embed_many(self,texts):
            sync_projection(newer,FakeEmbedder(newer.profile),activate=True)
            return super().embed_many(texts)
    with pytest.raises(KBConflict,match="Active snapshot changed"):
        sync_projection(p,Racing(p.profile),activate=True)
    with connect() as c:
        assert active_snapshot(c,p.namespace)==newer.snapshot_id


def test_corrupted_member_or_manifest_is_not_activated_or_retrieved():
    p = fixture_projection()
    provider = FakeEmbedder(p.profile)
    sync_projection(p,provider)
    with connect() as c:
        c.execute("UPDATE kb_snapshots SET chunk_count=chunk_count+1 WHERE namespace=%s",(p.namespace,))
    with pytest.raises(KBConflict,match="incomplete"):
        activate_snapshot(p.namespace,p.snapshot_id)
    assert KBRetriever(provider).retrieve(request_for(p)).fallback_reason=="retrieval_unavailable"


def test_out_of_scope_candidates_skip_embedding_entirely():
    p = fixture_projection()
    provider = FakeEmbedder(p.profile)
    sync_projection(p,provider)
    before = provider.calls
    result = KBRetriever(provider).retrieve(request_for(p,grade_levels=[12]))
    assert result.fallback_reason=="no_eligible_content" and provider.calls==before


def test_no_database_transaction_is_open_during_embedding():
    from contextlib import contextmanager
    opened = 0
    @contextmanager
    def tracked_connection():
        nonlocal opened
        with connect() as c:
            opened += 1
            try:
                yield c
            finally:
                opened -= 1
    p = fixture_projection(profile=fake_profile(revision="no-open-transaction"))
    class Checking(FakeEmbedder):
        def embed_many(self,texts):
            assert opened==0
            return super().embed_many(texts)
    provider = Checking(p.profile)
    sync_projection(p,provider,connection_factory=tracked_connection)
    assert KBRetriever(provider,tracked_connection).retrieve(request_for(p)).chunks


def test_runtime_tool_binds_only_canonical_pair_and_pins_snapshot():
    from app.kb_tool import bind_runtime_tool,TrustedKBState
    registry,bank,origin = load_source()
    p = project(registry,bank,load_profile(),origin=origin)
    class NoEmbedding:
        profile=p.profile
        def embed_many(self,texts):
            raise AssertionError("No approved chunks should reach embedding")
    sync_projection(p,NoEmbedding(),activate=True)
    state = TrustedKBState(session_id=uuid4(),opportunity_id=uuid4(),concept_id="A02",target_skill_id="SK-A02-DISTRIBUTE",
        allowed_hint_level=1,active_problem_id="SYNTHETIC-P",active_source_group="SYNTHETIC-SOURCE",
        active_family_id="SYNTHETIC-FAMILY",active_lineage_ids=("SYNTHETIC-LINEAGE",),grade_levels=(7,8),difficulty="standard")
    tool = bind_runtime_tool(state)
    result = tool.invoke({"query":"test", "concept_id":"A02","target_skill_id":"SK-A02-DISTRIBUTE","purpose":"hint"})
    assert result.kb_snapshot_version==p.snapshot_id and result.fallback_reason=="no_eligible_content"
    with pytest.raises(ValueError):
        bind_runtime_tool(replace(state,concept_id="CON-LINEAR-01",target_skill_id="SK-LIN-SOLVE"))


@pytest.mark.parametrize("failure",["count","dimension","zero","nonfinite"])
def test_malformed_embedding_batch_cannot_publish(failure):
    p = fixture_projection(profile=fake_profile(revision="malformed-"+failure))
    class Malformed(FakeEmbedder):
        def embed_many(self,texts):
            if failure=="count": return []
            vector = [1,0] if failure=="dimension" else [0,0,0] if failure=="zero" else [float("nan"),1,1]
            return [vector for _ in texts]
    with pytest.raises(ValueError):
        sync_projection(p,Malformed(p.profile),activate=True)
    assert counts(p.namespace)["kb_snapshots"]==counts(p.namespace)["kb_chunks"]==0


def test_withdrawal_during_query_embedding_is_rechecked_before_ranking():
    p = fixture_projection()
    class RevokingQuery(FakeEmbedder):
        def embed_query(self,text):
            withdraw_pack(p.namespace,"A02","0.1.0","withdrawal during query inference","synthetic test")
            return super().embed_query(text)
    provider = RevokingQuery(p.profile)
    sync_projection(p,provider)
    result = KBRetriever(provider).retrieve(request_for(p))
    assert result.chunks==[] and result.fallback_reason=="no_eligible_content" and result.eligible_count==0


def test_payload_corruption_fails_closed_before_returning_content():
    p = fixture_projection()
    sync_projection(p,FakeEmbedder(p.profile))
    with connect() as c:
        c.execute("""UPDATE kb_chunks SET payload=jsonb_set(payload,'{text}','\"CORRUPTED PRIVATE CONTENT\"'::jsonb)
            WHERE namespace=%s AND content_id='A02-hint-1'""",(p.namespace,))
    result = KBRetriever().retrieve(request_for(p,method="direct",level=1))
    assert result.chunks==[] and result.fallback_reason=="retrieval_unavailable"


def test_trace_persistence_failure_does_not_return_untraceable_content():
    from contextlib import contextmanager
    p = fixture_projection()
    sync_projection(p,FakeEmbedder(p.profile))
    calls = 0
    @contextmanager
    def unavailable_audit_connection():
        nonlocal calls
        calls += 1
        if calls==2:  # Direct lookup reads once, then writes its trace.
            raise ConnectionError("synthetic audit storage failure")
        with connect() as c:
            yield c
    result = KBRetriever(connection_factory=unavailable_audit_connection).retrieve(request_for(p,method="direct",level=1))
    assert result.chunks==[] and result.fallback_reason=="retrieval_unavailable"
