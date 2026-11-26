"""Stage 3 audit; optional real DB/local-embedding acceptance, never model API calls."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT,ROOT / "backend",ROOT / "scripts/exports",ROOT / "scripts/checks",ROOT / "scripts/kb",ROOT / "tests"):
    sys.path.insert(0,str(path))

from app.db import connect
from app.embeddings import LocalEmbedder
from app.kb_cli import default_model_dir
from app.kb_contracts import KBRequest,KBScope
from app.kb_projection import load_example_publications,load_profile,load_source,project
from app.kb_sync import active_snapshot,plan_sync,sync_projection,withdraw_pack
from app.manage import digest,migrate
from app.member2_contracts import RetrievalQuery
from app.retrieval import KBRetriever
from build_member2_stage3_assets import assets as expected_assets
from export_kb_contracts import audit as schema_audit
from research.retrieval.metrics import aggregate,score


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit():
    profile = load_profile()
    drafts = []
    draft_names = []
    for source in ("curriculum",):
        registry,bank,origin = load_source(source)
        drafts.append(project(registry,bank,profile,origin=origin))
        draft_names.append(source)
    if any(p.chunks for p in drafts):
        raise ValueError("Real draft sources unexpectedly became publishable")
    registry,bank,origin = load_source("member2-v2")
    publications = load_example_publications("member2-v2")
    approved = project(registry,bank,profile,origin=origin,examples=publications)
    if len(bank.packs)!=13 or len(publications)!=39 or len(approved.chunks)!=91 or approved.blocked:
        raise ValueError("Approved 13-concept KB publication is incomplete")
    generated = expected_assets()
    for path, expected in generated.items():
        if not path.is_file() or path.read_bytes()!=expected:
            raise ValueError("Missing or stale Stage 3 asset: " + str(path.relative_to(ROOT)))
    return {"version":"kb-1.0.0","schemas_checked":len(schema_audit(True)),
            "draft_source_runtime_chunks":{name:len(p.chunks) for name,p in zip(draft_names,drafts)},
            "retired_sources":"Removed by user request; only maintained sources are audited",
            "human_approved_real_packs":len(bank.packs),"published_examples":len(publications),
            "runtime_chunks":len(approved.chunks),"runtime_concepts":len({c.concept_id for c in approved.chunks}),
            "benchmark_queries":104,"profile_id":profile.profile_id,"dimension":profile.dimension,
            "model_api_calls":0}



@contextmanager
def isolated_acceptance_schema(run_id):
    """Run destructive acceptance operations only in a newly-created schema."""
    name = "stage3_check_" + run_id
    if not re.fullmatch(r"[0-9a-f]{12}",run_id):
        raise ValueError("Unsafe acceptance schema name")
    previous = os.environ.get("PGOPTIONS")
    before = serving_state()
    receipt = {"schema":name,"serving_before":before,"schema_removed":False}
    created = False
    try:
        # No pre-existing schema is reused or removed, even when CREATE fails.
        os.environ.pop("PGOPTIONS",None)
        with connect() as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
        created = True
        os.environ["PGOPTIONS"] = "-c search_path=" + name
        with connect() as connection:
            if connection.execute("SELECT current_schema() AS name").fetchone()["name"] != name:
                raise ValueError("Acceptance connection is outside its isolated schema")
            if connection.execute("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema=%s",(name,)).fetchone()["n"]:
                raise ValueError("Acceptance schema was not fresh")
            migrate(connection)
        yield receipt
    finally:
        if previous is None:
            os.environ.pop("PGOPTIONS",None)
        else:
            os.environ["PGOPTIONS"] = previous
        if created:
            with connect() as connection:
                connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))
                receipt["schema_removed"] = not connection.execute(
                    "SELECT 1 FROM pg_namespace WHERE nspname=%s",(name,)).fetchone()
        receipt["serving_after"] = serving_state()
        if receipt["serving_after"] != before:
            raise ValueError("Acceptance modified the serving KB outside its isolated schema")


def serving_state():
    """Fingerprint the caller's serving tables without relying on their contents."""
    with connect() as connection:
        if not connection.execute("SELECT to_regclass('kb_channels') AS name").fetchone()["name"]:
            return {"migrated":False}
        channel = connection.execute("SELECT snapshot_id FROM kb_channels WHERE namespace='runtime'").fetchone()
        counts = {table:connection.execute(sql.SQL("SELECT count(*) AS n FROM {} WHERE namespace='runtime'")
                    .format(sql.Identifier(table))).fetchone()["n"]
                  for table in ("kb_registry_versions","kb_chunks","kb_snapshot_members","kb_sync_runs",
                                "kb_withdrawals","kb_retrieval_traces")}
        return {"migrated":True,"active_snapshot":channel["snapshot_id"] if channel else None,"counts":counts}


def make_request(projection, query, method="semantic", direct_ref=None):
    scope = KBScope(namespace=projection.namespace,session_id=uuid4(),opportunity_id=uuid4(),
        allowed_targets=[{"concept_id":query["concept_id"],"skill_id":query["target_skill_id"]}],
        allowed_hint_level=query["allowed_hint_level"],kb_snapshot_version=projection.snapshot_id,
        active_problem_id=query["active_problem_id"],excluded_source_groups=query["excluded_source_groups"],
        excluded_family_ids=query["excluded_family_ids"],excluded_lineage_ids=query["excluded_lineage_ids"],
        grade_levels=query["grade_levels"],difficulty=query["difficulty"])
    return KBRequest(request_id=uuid4(),query=RetrievalQuery(query=query["query"],concept_id=query["concept_id"],
        target_skill_id=query["target_skill_id"],purpose=query["purpose"],top_k=query["top_k"]),
        scope=scope,method=method,direct_ref=direct_ref)


def metric_summary(rows):
    return {"cutoffs":{str(k):aggregate([row["metrics"][str(k)] for row in rows]) for k in (1,3,5)},
            "fallback_count":sum(not row["ids"] for row in rows),"query_count":len(rows)}


def real_acceptance(run_id, schema_name):
    profile = load_profile()
    registry,bank,origin = load_source("member2-v2")
    publications = load_example_publications("member2-v2")
    runtime = project(registry,bank,profile,origin=origin,examples=publications)
    embedder = LocalEmbedder(profile,default_model_dir(profile))
    with connect() as c:
        before = c.execute("SELECT count(*) AS n FROM kb_sync_runs").fetchone()["n"]
    _,plan = plan_sync(runtime)
    with connect() as c:
        after = c.execute("SELECT count(*) AS n FROM kb_sync_runs").fetchone()["n"]
    if before != after or embedder._model is not None or plan["new_chunk_versions"]!=91:
        raise ValueError("Dry-run performed writes or inference")
    first = sync_projection(runtime,embedder,activate=True)
    second = sync_projection(runtime,embedder,activate=True)
    if first["chunks"]!=91 or second["inserted_chunks"] or second["computed_embeddings"]:
        raise ValueError("Repeat sync is not idempotent")
    retriever = KBRetriever(embedder)
    dev = ROOT / "research/retrieval/dev/member2-13.v1"
    manifest,queries,qrels = read(dev / "manifest.json"),read(dev / "queries.json"),read(dev / "qrels.json")
    if manifest["snapshot_id"]!=runtime.snapshot_id or len(queries)!=104 or len(qrels)!=169:
        raise ValueError("13-concept benchmark does not match the runtime snapshot")
    direct_query = next(query for query in queries if query["query_id"]=="M2-A01-HINT-1")
    direct_request = make_request(runtime,direct_query,"direct",{
        "content_id":"A01-hint-1","content_version":runtime.registry.content_version})
    before_direct = embedder.calls
    direct = retriever.retrieve(direct_request)
    direct_embedding_calls = embedder.calls-before_direct
    if not direct.chunks or direct_embedding_calls:
        raise ValueError("Direct lookup unexpectedly needed embedding")
    rankings = {"metadata":[],"semantic":[]}
    for query in queries:
        grades = {row["content_id"]:row["relevance"] for row in qrels if row["query_id"]==query["query_id"]}
        expected_ids = set(query["eligible_candidate_ids"])
        for mode in rankings:
            request = make_request(runtime,query,mode)
            result = retriever.retrieve(request)
            ids = [ch.content_id for ch in result.chunks]
            if set(ids)!=expected_ids or result.fallback_reason not in (None,"no_eligible_content"):
                raise ValueError("Runtime filters disagree with 13-concept dev eligibility")
            rankings[mode].append({"query_id":query["query_id"],"retrieval_id":str(result.retrieval_id),
                "request_id":str(request.request_id),"ids":ids,"elapsed_ms":result.elapsed_ms,
                "eligible_count":result.eligible_count,"fallback_reason":result.fallback_reason,
                "metrics":{str(k):score(ids,grades,k) for k in (1,3,5)}})
    summary = {mode:metric_summary(rows) for mode,rows in rankings.items()}
    per_concept = {mode:{concept:metric_summary([row for row in rows if row["query_id"].startswith("M2-"+concept+"-")])
                         for concept in manifest["concept_ids"]} for mode,rows in rankings.items()}
    if any(s["fallback_count"]!=13 for s in summary.values()):
        raise ValueError("Fallback acceptance failed")

    fixture = project(registry,bank,profile,namespace="fixture-stage3-"+run_id,origin=origin,examples=publications)
    fixture_receipt = sync_projection(fixture,embedder,activate=True)
    fixture_direct_request = make_request(fixture,direct_query,"direct",{
        "content_id":"A01-hint-1","content_version":fixture.registry.content_version})
    withdrawal = withdraw_pack(fixture.namespace,"A01",fixture.registry.content_version,
        "Isolated Stage 3 withdrawal acceptance","Stage 3 checker")
    withdrawn_result = retriever.retrieve(fixture_direct_request)
    if withdrawn_result.chunks or withdrawn_result.fallback_reason!="no_eligible_content":
        raise ValueError("Pinned old snapshot did not respect withdrawal")
    effective,withdrawal_plan = plan_sync(fixture)
    next_receipt = sync_projection(fixture,embedder,activate=True)
    if any(ch.concept_id=="A01" for ch in effective.chunks) or len(effective.chunks)!=84:
        raise ValueError("New snapshot includes withdrawn content")
    with connect() as c:
        current_runtime = active_snapshot(c,"runtime")
        current_fixture = active_snapshot(c,fixture.namespace)
        traces = c.execute("SELECT count(*) AS n FROM kb_retrieval_traces").fetchone()["n"]
        trace_rows = c.execute("SELECT * FROM kb_retrieval_traces ORDER BY created_at,retrieval_id").fetchall()
        pg = c.execute("SELECT version() AS version").fetchone()["version"]
        vector = c.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()["extversion"]
    return {"isolated_schema":schema_name,"isolated_schema_fresh":True,"postgres":pg,"pgvector":vector,
        "runtime_plan":plan,"runtime_sync_first":first,"runtime_sync_second":second,
        "runtime_active_snapshot":current_runtime,"runtime_direct_result":direct.model_dump(mode="json"),
        "fixture_namespace":fixture.namespace,"fixture_sync":fixture_receipt,
        "model_profile":profile.model_dump(mode="json"),"local_embedding_texts_computed":embedder.calls,
        "direct_embedding_calls":direct_embedding_calls,
        "queries_sha256":digest(queries),"qrels_sha256":digest(qrels),
        "dev_rankings_before_withdrawal":rankings,"dev_summary":summary,"retrieval_traces":traces,
        "retrieval_trace_data":json.loads(json.dumps(trace_rows,default=str)),
        "dev_summary_by_concept":per_concept,
        "withdrawal":withdrawal,"withdrawn_old_snapshot_result":withdrawn_result.model_dump(mode="json"),
        "withdrawal_plan":withdrawal_plan,"withdrawal_sync":next_receipt,"fixture_active_snapshot":current_fixture,
        "real_runtime_approved_packs":13,"real_runtime_approved_chunks":91,"published_examples":39,
        "model_api_calls":0,"agent_response_integration":False,
        "limitations":["104-query relevance labels are deterministic development judgments, not independent human gold.",
                       "The dev benchmark covers all 13 approved concepts but is not the final held-out RQ3 evaluation.",
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
        with isolated_acceptance_schema(run_id) as isolation:
            result["acceptance"] = real_acceptance(run_id,isolation["schema"])
        result["acceptance"]["isolation"] = isolation
        out = ROOT / "artifacts/stage3-validation" / run_id / "acceptance.json"
        out.parent.mkdir(parents=True,exist_ok=False)
        with out.open("x",encoding="utf-8") as stream:
            stream.write(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
        print(json.dumps({"status":"passed","evidence":str(out.relative_to(ROOT)),"runtime_approved_chunks":91,
            "runtime_packs":13,"published_examples":39,"benchmark_queries":104,"model_api_calls":0,
            "semantic_ndcg_at_3":result["acceptance"]["dev_summary"]["semantic"]["cutoffs"]["3"]["ndcg"]["mean"]},indent=2))
    else:
        print(json.dumps({"status":"passed",**result},ensure_ascii=True,indent=2))


if __name__ == "__main__":
    main()
