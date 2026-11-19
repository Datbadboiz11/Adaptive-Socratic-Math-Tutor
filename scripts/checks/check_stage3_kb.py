"""Stage 3 audit; optional real DB/local-embedding acceptance, never model API calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT,ROOT / "backend",ROOT / "scripts/exports",ROOT / "scripts/checks",ROOT / "tests"):
    sys.path.insert(0,str(path))

from app.db import connect
from app.embeddings import LocalEmbedder
from app.kb_cli import default_model_dir
from app.kb_contracts import KBRequest,KBScope
from app.kb_projection import load_profile,load_source,project
from app.kb_sync import active_snapshot,plan_sync,sync_projection,withdraw_pack
from app.manage import digest
from app.member2_contracts import RetrievalQuery
from app.retrieval import KBRetriever
from check_member2_ai_review import audit as ai_audit
from export_kb_contracts import audit as schema_audit
from research.retrieval.metrics import aggregate,score


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit():
    profile = load_profile()
    projections = []
    for source in ("curriculum","oatutor-v2"):
        registry,bank,origin = load_source(source)
        projections.append(project(registry,bank,profile,origin=origin))
    if any(p.chunks for p in projections):
        raise ValueError("Real draft sources unexpectedly became publishable")
    return {"version":"kb-1.0.0","schemas_checked":len(schema_audit(True)),
            "real_sources_runtime_chunks":{name:len(p.chunks) for name,p in zip(("curriculum","oatutor-v2"),projections)},
            "human_approved_real_packs":0,"profile_id":profile.profile_id,"dimension":profile.dimension,
            "frozen_ai_review":ai_audit(),"model_api_calls":0}


def real_acceptance(run_id):
    # Approvals are explicitly synthetic and isolated to fixture-*; source files stay draft.
    from kb_support import fixture_projection,request_for
    profile = load_profile()
    registry,bank,origin = load_source()
    runtime = project(registry,bank,profile,origin=origin)
    runtime_embedder = LocalEmbedder(profile,default_model_dir(profile))
    with connect() as c:
        before = c.execute("SELECT count(*) AS n FROM kb_sync_runs").fetchone()["n"]
    _,plan = plan_sync(runtime)
    with connect() as c:
        after = c.execute("SELECT count(*) AS n FROM kb_sync_runs").fetchone()["n"]
    if before != after or runtime_embedder._model is not None:
        raise ValueError("Dry-run performed writes or inference")
    first = sync_projection(runtime,runtime_embedder,activate=True)
    second = sync_projection(runtime,runtime_embedder,activate=True)
    if first["chunks"] or second["inserted_chunks"] or runtime_embedder.calls:
        raise ValueError("Real draft publication boundary failed")
    empty = KBRetriever().retrieve(request_for(runtime,method="metadata"))
    if empty.chunks or empty.fallback_reason != "no_eligible_content":
        raise ValueError("Runtime drafts became retrievable")

    fixture = fixture_projection(namespace="fixture-stage3-"+run_id,profile=profile)
    embedder = LocalEmbedder(profile,default_model_dir(profile))
    receipt = sync_projection(fixture,embedder,activate=True)
    again = sync_projection(fixture,embedder,activate=True)
    if again["inserted_chunks"] or again["computed_embeddings"]:
        raise ValueError("Repeat sync is not idempotent")
    retriever = KBRetriever(embedder)
    direct_request = request_for(fixture,method="direct",level=1)
    before_direct = embedder.calls
    direct = retriever.retrieve(direct_request)
    direct_embedding_calls = embedder.calls-before_direct
    if not direct.chunks or direct_embedding_calls:
        raise ValueError("Direct lookup unexpectedly needed embedding")

    dev = ROOT / "research/retrieval/dev/a02-e02.ai-review.v1"
    queries,qrels = read(dev / "queries.json"),read(dev / "qrels.json")
    corpus = read(ROOT / "content/authoring/batches/a02-e02-oatutor.v2/retrieval-dev/corpus.json")
    mapping = {}
    for chunk in fixture.chunks:
        matches = [doc for doc in corpus["documents"] if doc["concept_id"]==chunk.concept_id
                   and doc["kind"]==chunk.kind and doc["hint_level"]==chunk.hint_level and doc["text"]==chunk.text]
        if len(matches)!=1:
            raise ValueError("Projected runtime text differs from the frozen dev corpus")
        mapping[matches[0]["content_id"]] = chunk.content_id
    if len(mapping)!=8:
        raise ValueError("Incomplete mapping to frozen dev qrels")
    rankings = {"metadata":[],"semantic":[]}
    problems = {p.case_id:p for pack in bank.packs for p in pack.problems}
    for query in queries:
        problem = problems[query["active_problem_id"]]
        scope = KBScope(namespace=fixture.namespace,session_id=uuid4(),opportunity_id=uuid4(),
            allowed_targets=[{"concept_id":query["concept_id"],"skill_id":query["target_skill_id"]}],
            allowed_hint_level=query["allowed_hint_level"],kb_snapshot_version=fixture.snapshot_id,
            active_problem_id=query["active_problem_id"],excluded_source_groups=query["excluded_source_groups"],
            excluded_family_ids=[problem.family_id],excluded_lineage_ids=[problem.source_group],
            grade_levels=query["grade_levels"],difficulty=problem.difficulty)
        grades = {mapping[r["content_id"]]:r["relevance"] for r in qrels if r["query_id"]==query["query_id"]}
        expected_ids = {mapping[cid] for cid in query["eligible_candidate_ids"]}
        for mode in rankings:
            request = KBRequest(request_id=uuid4(),query=RetrievalQuery(query=query["query"],concept_id=query["concept_id"],
                target_skill_id=query["target_skill_id"],purpose=query["purpose"],top_k=5),scope=scope,method=mode)
            result = retriever.retrieve(request)
            ids = [ch.content_id for ch in result.chunks]
            if set(ids)!=expected_ids or result.fallback_reason not in (None,"no_eligible_content"):
                raise ValueError("Runtime filters disagree with frozen dev eligibility")
            rankings[mode].append({"query_id":query["query_id"],"retrieval_id":str(result.retrieval_id),
                "request_id":str(request.request_id),"ids":ids,"elapsed_ms":result.elapsed_ms,
                "eligible_count":result.eligible_count,"fallback_reason":result.fallback_reason,
                "metrics":{str(k):score(ids,grades,k) for k in (1,3,5)}})
    summary = {mode:{"cutoffs":{str(k):aggregate([r["metrics"][str(k)] for r in rows]) for k in (1,3,5)},
                     "fallback_count":sum(not r["ids"] for r in rows)} for mode,rows in rankings.items()}
    if any(s["fallback_count"]!=4 for s in summary.values()):
        raise ValueError("Fallback acceptance failed")

    withdrawal = withdraw_pack(fixture.namespace,"A02","0.1.0","Synthetic revocation acceptance only","Codex synthetic acceptance")
    withdrawn_result = retriever.retrieve(direct_request)
    if withdrawn_result.chunks or withdrawn_result.fallback_reason!="no_eligible_content":
        raise ValueError("Pinned old snapshot did not respect withdrawal")
    effective,withdrawal_plan = plan_sync(fixture)
    next_receipt = sync_projection(fixture,embedder,activate=True)
    if any(ch.concept_id=="A02" for ch in effective.chunks) or len(effective.chunks)!=4:
        raise ValueError("New snapshot includes withdrawn content")
    with connect() as c:
        current_runtime = active_snapshot(c,"runtime")
        current_fixture = active_snapshot(c,fixture.namespace)
        traces = c.execute("SELECT count(*) AS n FROM kb_retrieval_traces WHERE namespace=%s",(fixture.namespace,)).fetchone()["n"]
        pg = c.execute("SELECT version() AS version").fetchone()["version"]
        vector = c.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()["extversion"]
    return {"postgres":pg,"pgvector":vector,"runtime_plan":plan,"runtime_sync_first":first,"runtime_sync_second":second,
        "runtime_empty_result":empty.model_dump(mode="json"),"runtime_active_snapshot":current_runtime,
        "fixture_namespace":fixture.namespace,"fixture_approval_is_human_attestation":False,
        "fixture_sync_first":receipt,"fixture_sync_second":again,"fixture_direct_result":direct.model_dump(mode="json"),
        "model_profile":profile.model_dump(mode="json"),"local_embedding_texts_computed":embedder.calls,
        "direct_embedding_calls":direct_embedding_calls,
        "queries_sha256":digest(queries),"qrels_sha256":digest(qrels),"dev_content_id_mapping":mapping,
        "dev_rankings_before_withdrawal":rankings,"dev_summary":summary,"retrieval_traces":traces,
        "withdrawal":withdrawal,"withdrawn_old_snapshot_result":withdrawn_result.model_dump(mode="json"),
        "withdrawal_plan":withdrawal_plan,"withdrawal_sync":next_receipt,"fixture_active_snapshot":current_fixture,
        "real_runtime_approved_chunks":0,"model_api_calls":0,"agent_response_integration":False,
        "limitations":["Positive retrieval uses synthetic approval provenance in fixture-* only, not human approval.",
                       "24 queries/8 chunks with AI-reviewed dev labels; no final RQ3 performance claim.",
                       "Live student Agent integration, assistance delivery, replay and UI citations are Chặng 4."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-local",action="store_true")
    parser.add_argument("--real-db",action="store_true")
    args = parser.parse_args()
    if args.workspace_local:
        sys.path.insert(0,str(ROOT / "scripts/dev"))
        from validation_runtime import local_environment
        os.environ.update(local_environment())
    # This check never needs a live LLM key and must not use one accidentally.
    for name in ("OPENAI_API_KEY","GEMINI_API_KEY"):
        os.environ.pop(name,None)
    result = {"checked_at":datetime.now(timezone.utc).isoformat(),"audit":audit()}
    if args.real_db:
        run_id = uuid4().hex[:12]
        result["acceptance"] = real_acceptance(run_id)
        out = ROOT / "artifacts/stage3-validation" / run_id / "acceptance.json"
        out.parent.mkdir(parents=True,exist_ok=False)
        with out.open("x",encoding="utf-8") as stream:
            stream.write(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
        print(json.dumps({"status":"passed","evidence":str(out.relative_to(ROOT)),"runtime_approved_chunks":0,
            "fixture_queries":24,"fixture_chunks":8,"model_api_calls":0,
            "semantic_ndcg_at_3":result["acceptance"]["dev_summary"]["semantic"]["cutoffs"]["3"]["ndcg"]["mean"]},indent=2))
    else:
        print(json.dumps({"status":"passed",**result},ensure_ascii=True,indent=2))


if __name__ == "__main__":
    main()
