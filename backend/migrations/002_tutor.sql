ALTER TABLE sessions ADD COLUMN tutoring_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE opportunities ADD COLUMN no_progress_count integer NOT NULL DEFAULT 0 CHECK (no_progress_count >= 0);
ALTER TABLE opportunities ADD COLUMN best_progress integer NOT NULL DEFAULT 0 CHECK (best_progress >= 0);
ALTER TABLE turns ADD COLUMN pipeline jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE knowledge_states (
    student_id text NOT NULL REFERENCES profiles,
    skill_id text NOT NULL,
    mastery double precision NOT NULL CHECK (mastery BETWEEN 0 AND 1),
    evidence_count integer NOT NULL CHECK (evidence_count >= 0),
    parameter_version text NOT NULL,
    PRIMARY KEY (student_id,skill_id)
);
CREATE TABLE turn_jobs (
    student_id text NOT NULL,
    session_id uuid NOT NULL,
    request_id uuid NOT NULL,
    payload_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('preparing','ready','committed')),
    lease_id uuid NOT NULL,
    lease_until timestamptz NOT NULL,
    prepared jsonb,
    FOREIGN KEY (session_id,student_id) REFERENCES sessions(session_id,student_id),
    PRIMARY KEY (student_id,session_id,request_id)
);
CREATE TABLE tutor_checkpoints (
    thread_id text NOT NULL,
    checkpoint_ns text NOT NULL,
    checkpoint_id text NOT NULL,
    parent_id text,
    checkpoint_type text NOT NULL,
    checkpoint bytea NOT NULL,
    metadata_type text NOT NULL,
    metadata bytea NOT NULL,
    PRIMARY KEY (thread_id,checkpoint_ns,checkpoint_id)
);
CREATE TABLE tutor_checkpoint_writes (
    thread_id text NOT NULL,
    checkpoint_ns text NOT NULL,
    checkpoint_id text NOT NULL,
    task_id text NOT NULL,
    idx integer NOT NULL,
    channel text NOT NULL,
    value_type text NOT NULL,
    value bytea NOT NULL,
    PRIMARY KEY (thread_id,checkpoint_ns,checkpoint_id,task_id,idx)
);
