"""Explicit download of pinned safetensors/tokenizer files; never called by requests."""
import argparse
from pathlib import Path
from app.qwen_query import MODEL_ID, MODEL_REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path('data/models/qwen3-4b'))
    parser.add_argument('--download', action='store_true', required=True,
                        help='Downloads about 8 GB; no training or model switching')
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    path = snapshot_download(MODEL_ID, revision=MODEL_REVISION, cache_dir=str(args.cache),
                             allow_patterns=['*.json', '*.safetensors', '*.txt'])
    print(f'Cached pinned Qwen model: {path}')


if __name__ == '__main__':
    main()
