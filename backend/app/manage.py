"""Versioned migrations and immutable, repeatable content seed. No destructive reset."""
import argparse
import hashlib
import json
from pathlib import Path

from psycopg.types.json import Jsonb
from app.db import connect
from app.contracts import ContentBank

BASE = Path(__file__).resolve().parents[1]
CONTENT = BASE.parent / 'content' / 'linear_equations.v1.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def migrate(connection):
    connection.execute("SELECT pg_advisory_xact_lock(791201)")
    connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
    applied = []
    for path in sorted((BASE / 'migrations').glob('*.sql')):
        sql = path.read_text(encoding='utf-8')
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        old = connection.execute('SELECT checksum FROM schema_migrations WHERE name=%s', (path.name,)).fetchone()
        if old:
            if old['checksum'] != checksum:
                raise ValueError(f'Migration changed after application: {path.name}')
            continue
        connection.execute(sql)
        connection.execute('INSERT INTO schema_migrations(name,checksum) VALUES (%s,%s)', (path.name, checksum))
        applied.append(path.name)
    return applied


def seed(connection, path=CONTENT):
    bank = ContentBank.model_validate_json(path.read_text(encoding='utf-8'))
    connection.execute('SELECT pg_advisory_xact_lock(791202)')
    connection.execute('INSERT INTO topics VALUES (%s,%s) ON CONFLICT DO NOTHING', (bank.topic_id, bank.title))
    for student, name in [('DEMO-STUDENT-01', 'Minh Anh · hồ sơ demo'), ('DEMO-STUDENT-02', 'Gia Huy · hồ sơ demo')]:
        connection.execute('INSERT INTO profiles(student_id,display_name) VALUES (%s,%s) ON CONFLICT DO NOTHING', (student, name))
    inserted = 0
    for problem in bank.problems:
        payload = problem.model_dump(mode='json')
        checksum = digest(payload)
        old = connection.execute('SELECT content_hash FROM problems WHERE problem_id=%s AND content_version=%s', (problem.problem_id, problem.content_version)).fetchone()
        if old:
            if old['content_hash'] != checksum:
                raise ValueError(f'Content version is immutable: {problem.problem_id}; create a new version')
            continue
        connection.execute('''INSERT INTO problems
            (problem_id,content_version,topic_id,family_id,source_group,primary_skill_id,review_status,public_payload,private_payload,content_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (problem.problem_id, problem.content_version, bank.topic_id, problem.family_id, problem.source_group,
             problem.primary_skill_id, problem.review.status, Jsonb(problem.to_public().model_dump(mode='json')), Jsonb(payload), checksum))
        inserted += 1
    return {'inserted': inserted, 'total_in_bank': len(bank.problems), 'human_review': 'unchanged'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['migrate', 'seed', 'bootstrap'])
    args = parser.parse_args()
    with connect() as connection:
        result = {}
        if args.command in ('migrate', 'bootstrap'):
            result['migrations'] = migrate(connection)
        if args.command in ('seed', 'bootstrap'):
            result['seed'] = seed(connection)
    print(json.dumps(result))
