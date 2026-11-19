-- Isolated tests use their own search_path; extension types/operators always use public.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

CREATE TABLE kb_registry_versions (
    namespace text NOT NULL,
    registry_version text NOT NULL,
    registry_hash text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY(namespace,registry_version),
    CHECK(namespace='runtime' OR namespace ~ '^fixture-[A-Za-z0-9-]{1,50}$')
);
CREATE TABLE kb_concepts (
    namespace text NOT NULL, registry_version text NOT NULL, concept_id text NOT NULL, payload jsonb NOT NULL,
    PRIMARY KEY(namespace,registry_version,concept_id),
    FOREIGN KEY(namespace,registry_version) REFERENCES kb_registry_versions(namespace,registry_version)
);
CREATE TABLE kb_skills (
    namespace text NOT NULL, registry_version text NOT NULL, concept_id text NOT NULL,
    skill_id text NOT NULL, payload jsonb NOT NULL,
    PRIMARY KEY(namespace,registry_version,skill_id),
    UNIQUE(namespace,registry_version,concept_id,skill_id),
    FOREIGN KEY(namespace,registry_version,concept_id) REFERENCES kb_concepts(namespace,registry_version,concept_id)
);
CREATE TABLE kb_legacy_mappings (
    namespace text NOT NULL, registry_version text NOT NULL,
    legacy_concept_id text NOT NULL, legacy_skill_id text NOT NULL,
    concept_id text NOT NULL, skill_id text NOT NULL,
    status text NOT NULL CHECK(status='proposed'), payload jsonb NOT NULL,
    PRIMARY KEY(namespace,registry_version,legacy_concept_id,legacy_skill_id),
    FOREIGN KEY(namespace,registry_version,concept_id,skill_id)
        REFERENCES kb_skills(namespace,registry_version,concept_id,skill_id)
);
CREATE TABLE kb_embedding_profiles (
    profile_id text PRIMARY KEY, dimension integer NOT NULL CHECK(dimension BETWEEN 1 AND 4096),
    provider text NOT NULL CHECK(provider IN ('fastembed','synthetic_fixture')), configuration jsonb NOT NULL,
    UNIQUE(profile_id,dimension)
);
CREATE TABLE kb_chunks (
    namespace text NOT NULL, content_id text NOT NULL, content_version text NOT NULL,
    registry_version text NOT NULL, concept_id text NOT NULL, pack_version text NOT NULL,
    content_hash text NOT NULL, text_hash text NOT NULL, text text NOT NULL, payload jsonb NOT NULL,
    skill_ids text[] NOT NULL CHECK(cardinality(skill_ids)>0),
    kind text NOT NULL CHECK(kind IN ('explanation','hint','example')),
    hint_level integer NOT NULL CHECK(hint_level BETWEEN 0 AND 3),
    disclosure text NOT NULL CHECK(disclosure IN ('conceptual','strategy','scaffold','different_example')),
    grade_levels integer[] NOT NULL CHECK(cardinality(grade_levels)>0),
    difficulty text CHECK(difficulty IN ('introductory','standard')),
    problem_id text, source_group text, family_id text, lineage_ids text[] NOT NULL,
    PRIMARY KEY(namespace,content_id,content_version),
    UNIQUE(namespace,content_id,content_version,text_hash),
    FOREIGN KEY(namespace,registry_version,concept_id) REFERENCES kb_concepts(namespace,registry_version,concept_id),
    CHECK(payload->'review'->>'status'='human_approved'),
    CHECK((kind='explanation' AND hint_level=0 AND disclosure='conceptual')
       OR (kind='hint' AND ((hint_level=1 AND disclosure='conceptual') OR (hint_level=2 AND disclosure='strategy')
                         OR (hint_level=3 AND disclosure='scaffold')))
       OR (kind='example' AND hint_level=3 AND disclosure='different_example'
            AND problem_id IS NOT NULL AND source_group IS NOT NULL AND family_id IS NOT NULL AND cardinality(lineage_ids)>0))
);
CREATE TABLE kb_embeddings (
    profile_id text NOT NULL, text_hash text NOT NULL, dimension integer NOT NULL,
    embedding public.vector NOT NULL, vector_hash text NOT NULL,
    PRIMARY KEY(profile_id,text_hash),
    FOREIGN KEY(profile_id,dimension) REFERENCES kb_embedding_profiles(profile_id,dimension),
    CHECK(public.vector_dims(embedding)=dimension), CHECK(public.vector_norm(embedding)>0)
);
CREATE TABLE kb_snapshots (
    namespace text NOT NULL, snapshot_id text NOT NULL, registry_version text NOT NULL,
    profile_id text NOT NULL REFERENCES kb_embedding_profiles(profile_id),
    manifest_hash text NOT NULL, manifest jsonb NOT NULL, chunk_count integer NOT NULL CHECK(chunk_count>=0),
    ready_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(namespace,snapshot_id), UNIQUE(namespace,snapshot_id,profile_id),
    FOREIGN KEY(namespace,registry_version) REFERENCES kb_registry_versions(namespace,registry_version)
);
CREATE TABLE kb_snapshot_members (
    namespace text NOT NULL, snapshot_id text NOT NULL, content_id text NOT NULL, content_version text NOT NULL,
    profile_id text NOT NULL, text_hash text NOT NULL,
    PRIMARY KEY(namespace,snapshot_id,content_id,content_version),
    FOREIGN KEY(namespace,snapshot_id,profile_id) REFERENCES kb_snapshots(namespace,snapshot_id,profile_id),
    FOREIGN KEY(namespace,content_id,content_version,text_hash) REFERENCES kb_chunks(namespace,content_id,content_version,text_hash),
    FOREIGN KEY(profile_id,text_hash) REFERENCES kb_embeddings(profile_id,text_hash)
);
CREATE TABLE kb_channels (
    namespace text PRIMARY KEY, snapshot_id text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(namespace,snapshot_id) REFERENCES kb_snapshots(namespace,snapshot_id)
);
CREATE TABLE kb_withdrawals (
    namespace text NOT NULL, concept_id text NOT NULL, pack_version text NOT NULL,
    reason text NOT NULL CHECK(length(reason)>0), actor text NOT NULL CHECK(length(actor)>0),
    withdrawn_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(namespace,concept_id,pack_version)
);
CREATE TABLE kb_sync_runs (
    run_id uuid PRIMARY KEY, namespace text NOT NULL, snapshot_id text NOT NULL,
    status text NOT NULL CHECK(status IN ('preparing','published','failed')),
    started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
    summary jsonb NOT NULL, error_class text
);
CREATE TABLE kb_retrieval_traces (
    retrieval_id uuid PRIMARY KEY, request_id uuid NOT NULL,
    namespace text NOT NULL, snapshot_id text NOT NULL,
    query_hash text NOT NULL, scope_hash text NOT NULL,
    config_version text NOT NULL, method text NOT NULL,
    embedding_profile_id text, elapsed_ms double precision NOT NULL CHECK(elapsed_ms>=0),
    selected_refs jsonb NOT NULL, fallback_reason text, error_class text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX kb_chunks_scope ON kb_chunks(namespace,concept_id,kind,hint_level);
CREATE INDEX kb_retrieval_requests ON kb_retrieval_traces(request_id);
-- Exact search first. No ANN index until a measured query bottleneck justifies one.
