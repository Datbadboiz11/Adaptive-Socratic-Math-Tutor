"""Fail early when a checkout lacks files needed to run the maintained release."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = (
    'README.md', 'compose.yaml',
    'content/curriculum/registry.v2.json',
    'content/curriculum/pilot.v2.json',
    'content/curriculum/member2-workboard-confirmation.v1.json',
    'content/curriculum/member2-stage1-update-confirmation.v1.json',
    'content/authoring/prompts/draft.v1.txt',
    'content/authoring/prompts/draft.v2.txt',
    'content/authoring/batches/member2-original.v2/manifest.json',
    'content/authoring/batches/member2-original.v2/approved-bank.json',
    'content/authoring/batches/member2-original.v2/registry-snapshot.json',
)


def check(root):
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise ValueError('Required release inputs are missing: ' + ', '.join(missing))
    retired = [path.relative_to(root).as_posix()
               for folder in ('content/authoring', 'research/retrieval/dev')
               for path in (root / folder).rglob('*') if path.is_file()
               and re.search(r'(^|/)(a02|e02)([./_-]|$)|/a02-e02', path.relative_to(root).as_posix(), re.I)]
    if retired:
        raise ValueError('Retired per-concept source files must not be published: ' + ', '.join(retired))
    for name in REQUIRED:
        if name.endswith('.json'):
            json.loads((root / name).read_text(encoding='utf-8'))
    compose = (root / 'compose.yaml').read_text(encoding='utf-8')
    if '\n  db:' not in compose or '\n  neo4j:' not in compose:
        raise ValueError('compose.yaml must retain the shared PostgreSQL and Neo4j services')
    registry = json.loads((root / 'content/curriculum/registry.v2.json').read_text(encoding='utf-8'))
    if len(registry['concepts']) != 40:
        raise ValueError('The release registry must retain all 40 concepts')
    return {'status': 'passed', 'required_files': len(REQUIRED), 'registry_concepts': 40,
            'shared_services': ['db', 'neo4j']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.root)))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
