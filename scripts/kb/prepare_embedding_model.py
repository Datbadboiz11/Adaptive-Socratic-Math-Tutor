"""Fetch only the pinned public ONNX/tokenizer files; verify hashes, never overwrite mismatches."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "backend"))
from app.kb_cli import default_model_dir
from app.kb_projection import load_profile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--export-dir",type=Path,help="Copy verified files into a flat deployment directory without cache symlinks")
    args = parser.parse_args()
    profile = load_profile()
    target = (args.output_dir or default_model_dir(profile)).resolve()
    for name,expected in profile.files_sha256.items():
        path = target/name
        if path.exists() and sha(path)!=expected:
            raise SystemExit("Existing model file differs from pinned hash; choose another output directory")
    target.mkdir(parents=True,exist_ok=True)
    downloaded = 0
    for name,expected in profile.files_sha256.items():
        path = target/name
        if not path.exists():
            from huggingface_hub import hf_hub_download
            hf_hub_download(repo_id="Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q",filename=name,
                            revision=profile.revision,local_dir=target,token=False)
            downloaded += 1
        if sha(path)!=expected:
            raise SystemExit("Downloaded file checksum differs from pinned profile")
    if args.export_dir:
        deployment = args.export_dir.resolve()
        for name,expected in profile.files_sha256.items():
            path = deployment/name
            if path.exists() and sha(path)!=expected:
                raise SystemExit("Existing deployment file differs; choose another export directory")
            if path.is_symlink():
                raise SystemExit("Deployment directory must contain regular files; choose another export directory")
        deployment.mkdir(parents=True,exist_ok=True)
        for name,expected in profile.files_sha256.items():
            path = deployment/name
            if not path.exists():
                with (target/name).open("rb") as source, path.open("xb") as destination:
                    shutil.copyfileobj(source,destination)
            if sha(path)!=expected:
                raise SystemExit("Deployment copy checksum mismatch")
    print(json.dumps({"status":"verified","files":len(profile.files_sha256),"downloaded_files":downloaded,
                      "model_dir":str(target),"deployment_dir":str(args.export_dir.resolve()) if args.export_dir else None,
                      "profile_id":profile.profile_id,"model_api_calls":0},indent=2))


if __name__ == "__main__":
    main()
