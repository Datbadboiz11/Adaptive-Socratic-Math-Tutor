-- Separate opt-in RAG migration; does not change learner/session/BKT tables.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

CREATE TABLE IF NOT EXISTS rag_registry_snapshots (
    snapshot_id text PRIMARY KEY,
    payload jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_collections (
    collection_id text PRIMARY KEY,
    registry_snapshot_id text NOT NULL REFERENCES rag_registry_snapshots(snapshot_id),
    corpus_sha256 text NOT NULL,
    encoder jsonb NOT NULL,
    artifact_sha256 text NOT NULL,
    chunk_count integer NOT NULL CHECK (chunk_count > 0),
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    collection_id text NOT NULL REFERENCES rag_collections(collection_id),
    content_id text NOT NULL,
    concept_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('hint', 'explanation')),
    hint_level integer NOT NULL CHECK (hint_level BETWEEN 0 AND 3),
    approved boolean NOT NULL,
    content_version text NOT NULL,
    payload jsonb NOT NULL,
    embedding public.vector(2560) NOT NULL,
    PRIMARY KEY (collection_id, content_id),
    CHECK (public.vector_norm(embedding) BETWEEN 0.99999 AND 1.00001)
);
CREATE INDEX IF NOT EXISTS rag_chunks_metadata
    ON rag_chunks(collection_id, concept_id, kind, hint_level, approved);
-- Exact search is intentional: only 40 pilot chunks. vector HNSW has a 2000-dim
-- limit, so a vector(2560) HNSW index must not be created here.
