"""KB admin CLI: dry-run, atomic sync/activation, withdrawal and safe export."""
import argparse
import json
import os
from pathlib import Path
import sys

from pydantic import TypeAdapter
from app.curriculum import CurriculumRegistry, PilotBank
from app.db import connect
from app.embeddings import LocalEmbedder
from app.kb_contracts import ExamplePublication, Namespace
from app.kb_projection import ROOT, load_profile, load_source, project
from app.kb_sync import activate_snapshot, plan_sync, sync_projection, withdraw_pack


def default_model_dir(profile):
    return Path(os.getenv("KB_MODEL_DIR", str(ROOT / "artifacts/tooling/embedding-models"
        / "models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/snapshots" / profile.revision)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-local", action="store_true")
    parser.add_argument("--namespace", default="runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync")
    sync.add_argument("--source", choices=["oatutor-v2","curriculum"], default="oatutor-v2")
    sync.add_argument("--registry", type=Path)
    sync.add_argument("--bank", type=Path)
    sync.add_argument("--examples", type=Path)
    sync.add_argument("--profile", type=Path)
    sync.add_argument("--model-dir", type=Path)
    sync.add_argument("--dry-run", action="store_true")
    sync.add_argument("--activate", action="store_true")
    activation = sub.add_parser("activate")
    activation.add_argument("--snapshot", required=True)
    withdrawal = sub.add_parser("withdraw")
    withdrawal.add_argument("--concept", required=True)
    withdrawal.add_argument("--version", required=True)
    withdrawal.add_argument("--reason", required=True)
    withdrawal.add_argument("--actor", required=True)
    sub.add_parser("status")
    export = sub.add_parser("export")
    export.add_argument("--snapshot", required=True)
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        namespace = TypeAdapter(Namespace).validate_python(args.namespace)
        if args.workspace_local:
            sys.path.insert(0,str(ROOT / "scripts/dev"))
            from validation_runtime import local_environment
            os.environ.update(local_environment())
        if args.command == "sync":
            if bool(args.registry) != bool(args.bank):
                parser.error("Provide both --registry and --bank")
            if args.registry:
                registry = CurriculumRegistry.model_validate_json(args.registry.read_text(encoding="utf-8"))
                bank = PilotBank.model_validate_json(args.bank.read_text(encoding="utf-8"))
                origin = args.bank.name
            else:
                registry,bank,origin = load_source(args.source)
            examples = TypeAdapter(list[ExamplePublication]).validate_json(args.examples.read_text(encoding="utf-8")) if args.examples else []
            profile = load_profile(args.profile)
            p = project(registry,bank,profile,namespace=namespace,origin=origin,examples=examples)
            if args.dry_run:
                _,result = plan_sync(p)
                result = {**result,"dry_run":True,"database_writes":0,"embedding_calls":0,"activated":False}
            else:
                result = sync_projection(p,LocalEmbedder(profile,args.model_dir or default_model_dir(profile)),activate=args.activate)
        elif args.command == "activate":
            result = activate_snapshot(namespace,args.snapshot)
        elif args.command == "withdraw":
            result = withdraw_pack(namespace,args.concept,args.version,args.reason,args.actor)
        elif args.command == "status":
            with connect() as c:
                result = {"namespace":namespace,"snapshots":c.execute("SELECT snapshot_id,profile_id,chunk_count FROM kb_snapshots WHERE namespace=%s ORDER BY ready_at",(namespace,)).fetchall(),
                    "channel":c.execute("SELECT snapshot_id FROM kb_channels WHERE namespace=%s",(namespace,)).fetchone(),
                    "withdrawals":c.execute("SELECT concept_id,pack_version FROM kb_withdrawals WHERE namespace=%s",(namespace,)).fetchall()}
        else:
            with connect() as c:
                snapshot = c.execute("SELECT * FROM kb_snapshots WHERE namespace=%s AND snapshot_id=%s",(namespace,args.snapshot)).fetchone()
                if not snapshot:
                    raise ValueError("Unknown snapshot")
                registry = c.execute("SELECT payload FROM kb_registry_versions WHERE namespace=%s AND registry_version=%s",(namespace,snapshot["registry_version"])).fetchone()["payload"]
                chunks = c.execute("SELECT ch.payload FROM kb_snapshot_members m JOIN kb_chunks ch USING(namespace,content_id,content_version) WHERE m.namespace=%s AND m.snapshot_id=%s ORDER BY ch.content_id",(namespace,args.snapshot)).fetchall()
                withdrawals = c.execute("SELECT concept_id,pack_version FROM kb_withdrawals WHERE namespace=%s",(namespace,)).fetchall()
                channel = c.execute("SELECT snapshot_id FROM kb_channels WHERE namespace=%s",(namespace,)).fetchone()
            payload = {"namespace":namespace,"snapshot_id":args.snapshot,"manifest":snapshot["manifest"],"registry":registry,
                "chunks":[r["payload"] for r in chunks],"current_withdrawals":withdrawals,
                "active_at_export":bool(channel and channel["snapshot_id"]==args.snapshot),
                "usage":"archival_export_not_runtime_authorization"}
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open("x",encoding="utf-8") as stream:
                stream.write(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2)+"\n")
            result = {"snapshot_id":args.snapshot,"export_file":str(args.output),"chunks":len(chunks),"private_references_exported":False}
        print(json.dumps(result,ensure_ascii=True,indent=2))
    except Exception as error:
        # Source parsing/connection errors can contain private records or DSNs. Keep details local/in memory.
        print(json.dumps({"status":"failed","error_class":type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
