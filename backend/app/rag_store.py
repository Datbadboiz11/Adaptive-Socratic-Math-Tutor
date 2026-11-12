"""Immutable, versioned Qwen collections in PostgreSQL/pgvector. No publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from psycopg.types.json import Jsonb

from app.curriculum import load_curriculum
from app.curriculum_graph import snapshot_id
from app.db import connect
from app.local_embedding import EmbeddingUnavailable
from app.qwen_query import ENCODER, normalized
from app.retrieval import corpus, corpus_hash, digest, embedding_text

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent
DEFAULT_INPUTS = ROOT / 'data/retrieval/qwen3-4b-v1'


def collection_id(chunks, registry_id):
    return digest({'encoder': ENCODER, 'corpus_sha256': corpus_hash(chunks), 'registry_snapshot_id': registry_id})


def validate_index(document, chunks):
    try:
        if (document['schema_version'] != '1.0.0' or document['encoder'] != ENCODER
                or document['corpus_sha256'] != corpus_hash(chunks)):
            raise ValueError()
        rows = document['records']
        if len(rows) != len(chunks) or len({r['content_id'] for r in rows}) != len(chunks):
            raise ValueError()
        by_id = {r['content_id']: r for r in rows}
        if set(by_id) != {c.content_id for c in chunks}:
            raise ValueError()
        for c in chunks:
            if by_id[c.content_id]['text_sha256'] != digest(embedding_text(c)):
                raise ValueError()
        return {cid: normalized(row['vector']) for cid, row in by_id.items()}
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable('qwen_index_stale_or_invalid') from None


def read_artifact(directory, chunks):
    """Read JSON only, validate hashes and current corpus before opening a DB transaction."""
    directory = Path(directory)
    names = {'index.json', 'query-vectors.json', 'evaluation.json', 'corpus.json', 'queries.json', 'bge-baseline.json'}
    try:
        manifest_path = directory / 'run-manifest.json'
        if manifest_path.stat().st_size > 65536:
            raise ValueError()
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['schema_version'] != '1.0.0' or manifest['encoder'] != ENCODER or set(manifest['sha256']) != names:
            raise ValueError()
        if sum((directory / n).stat().st_size for n in names) > 20 * 1024**2:
            raise ValueError()
        raw = {n: (directory / n).read_bytes() for n in names}
        if any(hashlib.sha256(value).hexdigest() != manifest['sha256'][n] for n, value in raw.items()):
            raise ValueError()
        if (json.loads(raw['corpus.json']) != [c.model_dump(mode='json') for c in chunks]
                or manifest['corpus_sha256'] != corpus_hash(chunks)):
            raise ValueError()
        vectors = validate_index(json.loads(raw['index.json']), chunks)
        return vectors, hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable('qwen_artifact_invalid') from None


def vector_literal(vector):
    return '[' + ','.join(format(v, '.17g') for v in normalized(vector)) + ']'


def migrate(connection):
    """Explicit opt-in, separate from the MVP migration chain."""
    connection.execute('SELECT pg_advisory_xact_lock(791301)')
    connection.execute('''CREATE TABLE IF NOT EXISTS rag_schema_migrations (
        name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())''')
    for path in sorted((BASE / 'rag_migrations').glob('*.sql')):
        body = path.read_text(encoding='utf-8')
        sha = hashlib.sha256(body.encode()).hexdigest()
        old = connection.execute('SELECT checksum FROM rag_schema_migrations WHERE name=%s', (path.name,)).fetchone()
        if old:
            if old['checksum'] != sha:
                raise ValueError('RAG migration changed after application; add a new migration')
            continue
        connection.execute(body)
        connection.execute('INSERT INTO rag_schema_migrations(name,checksum) VALUES (%s,%s)', (path.name,sha))


def sync(connection, registry, chunks, vectors, artifact_sha):
    if set(vectors) != {c.content_id for c in chunks} or not chunks:
        raise ValueError('Vector coverage differs from current corpus')
    vectors = {key: normalized(value) for key,value in vectors.items()}
    rid = snapshot_id(registry)
    cid = collection_id(chunks, rid)
    connection.execute('SELECT pg_advisory_xact_lock(791302)')
    current = connection.execute('SELECT payload FROM rag_registry_snapshots WHERE snapshot_id=%s', (rid,)).fetchone()
    payload = registry.model_dump(mode='json')
    if current and current['payload'] != payload:
        raise ValueError('Existing registry snapshot differs; refusing overwrite')
    if not current:
        connection.execute('INSERT INTO rag_registry_snapshots(snapshot_id,payload) VALUES (%s,%s)', (rid, Jsonb(payload)))
    existing = connection.execute('SELECT * FROM rag_collections WHERE collection_id=%s', (cid,)).fetchone()
    if existing:
        if (existing['encoder'] != ENCODER or existing['corpus_sha256'] != corpus_hash(chunks)
                or existing['registry_snapshot_id'] != rid or existing['chunk_count'] != len(chunks)
                or existing['artifact_sha256'] != artifact_sha):
            raise ValueError('Existing collection differs; refusing overwrite')
        rows = connection.execute('SELECT content_id,payload,embedding::text AS embedding FROM rag_chunks WHERE collection_id=%s', (cid,)).fetchall()
        by_id = {r['content_id']: r for r in rows}
        if len(rows) != len(chunks) or set(by_id) != {c.content_id for c in chunks}:
            raise ValueError('Existing collection incomplete; refusing repair/overwrite')
        for c in chunks:
            r = by_id[c.content_id]
            actual = json.loads(r['embedding'])
            if (r['payload'] != c.model_dump(mode='json') or len(actual) != 2560
                    or any(abs(a-b) > 1e-7 for a,b in zip(actual, vectors[c.content_id]))):
                raise ValueError('Existing collection payload/vector differs; refusing overwrite')
        return {'collection_id': cid, 'inserted': 0, 'chunks': len(chunks), 'registry_snapshot_id': rid}
    connection.execute('''INSERT INTO rag_collections
        (collection_id,registry_snapshot_id,corpus_sha256,encoder,artifact_sha256,chunk_count)
        VALUES (%s,%s,%s,%s,%s,%s)''', (cid, rid, corpus_hash(chunks), Jsonb(ENCODER), artifact_sha, len(chunks)))
    for c in chunks:
        connection.execute('''INSERT INTO rag_chunks
            (collection_id,content_id,concept_id,kind,hint_level,approved,content_version,payload,embedding)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::public.vector(2560))''',
            (cid, c.content_id, c.concept_id, c.kind, c.hint_level, c.approved,
             c.content_version, Jsonb(c.model_dump(mode='json')), vector_literal(vectors[c.content_id])))
    return {'collection_id': cid, 'inserted': len(chunks), 'chunks': len(chunks), 'registry_snapshot_id': rid}


class PgVectorStore:
    def __init__(self, registry_id, connection_factory=None):
        self.registry_id = registry_id
        self.connection_factory = connection_factory or connect

    def _check(self, connection, chunks):
        # Extension catalog entries can survive switching back to a plain Postgres
        # image. Check that the installed vector library is actually callable.
        connection.execute("SELECT public.vector_dims('[1]'::public.vector)")
        cid = collection_id(chunks, self.registry_id)
        row = connection.execute('''SELECT encoder,corpus_sha256,chunk_count,registry_snapshot_id,
            (SELECT count(*) FROM rag_chunks c WHERE c.collection_id=r.collection_id) AS actual_count
            FROM rag_collections r WHERE collection_id=%s''', (cid,)).fetchone()
        if (not row or row['encoder'] != ENCODER or row['corpus_sha256'] != corpus_hash(chunks)
                or row['chunk_count'] != len(chunks) or row['actual_count'] != len(chunks)
                or row['registry_snapshot_id'] != self.registry_id):
            raise EmbeddingUnavailable('qwen_collection_missing_or_stale')
        return cid

    def ready(self, chunks):
        try:
            with self.connection_factory() as connection:
                connection.execute("SET LOCAL statement_timeout='3000ms'")
                return self._check(connection, chunks)
        except EmbeddingUnavailable:
            raise
        except Exception:
            raise EmbeddingUnavailable('pgvector_unavailable') from None

    def search(self, chunks, request, vector, pool, *, authoring=False):
        literal = vector_literal(vector)
        allowed = {c.content_id: c for c in pool}
        try:
            with self.connection_factory() as connection:
                connection.execute("SET LOCAL statement_timeout='3000ms'")
                cid = self._check(connection, chunks)
                rows = connection.execute('''SELECT content_id,payload,
                    1 - (embedding OPERATOR(public.<=>) %s::public.vector(2560)) AS score
                    FROM rag_chunks WHERE collection_id=%s AND content_id=ANY(%s)
                    AND concept_id=ANY(%s) AND kind=%s AND hint_level<=%s
                    AND (%s OR approved)
                    ORDER BY embedding OPERATOR(public.<=>) %s::public.vector(2560), content_id LIMIT %s''',
                    (literal, cid, list(allowed), request.concept_ids, request.purpose,
                     request.hint_level, authoring, literal, request.top_k)).fetchall()
            if any(r['content_id'] not in allowed or r['payload'] != allowed[r['content_id']].model_dump(mode='json') for r in rows):
                raise EmbeddingUnavailable('qwen_collection_payload_mismatch')
            if len({r['content_id'] for r in rows}) != len(rows):
                raise EmbeddingUnavailable('qwen_collection_payload_mismatch')
            return cid, [(allowed[r['content_id']], float(r['score'])) for r in rows]
        except EmbeddingUnavailable:
            raise
        except Exception:
            raise EmbeddingUnavailable('pgvector_unavailable') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['sync', 'status'])
    parser.add_argument('--inputs', type=Path, default=Path(os.getenv('QWEN_ARTIFACT_PATH', str(DEFAULT_INPUTS))))
    args = parser.parse_args()
    registry, bank = load_curriculum()
    chunks = corpus(registry, bank)
    if args.command == 'sync':
        vectors, sha = read_artifact(args.inputs, chunks)
        with connect() as connection:
            migrate(connection)
            result = sync(connection, registry, chunks, vectors, sha)
    else:
        result = {'collection_id': PgVectorStore(snapshot_id(registry)).ready(chunks)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
