-- Existing sessions retain their original behavior; new sessions pin retrieval mode/snapshot.
ALTER TABLE sessions ADD COLUMN rag_mode text NOT NULL DEFAULT 'no_rag' CHECK (rag_mode IN ('full','no_rag'));
ALTER TABLE sessions ADD COLUMN kb_snapshot_id text;
ALTER TABLE opportunities ADD COLUMN assistance_received boolean NOT NULL DEFAULT false;
UPDATE opportunities SET assistance_received=true WHERE assistance_level>0;
ALTER TABLE turns DROP CONSTRAINT turns_action_check;
ALTER TABLE turns ADD CONSTRAINT turns_action_check CHECK (action IN ('submit','request_hint','request_explanation','request_example'));
CREATE TABLE teaching_deliveries (
    turn_id uuid NOT NULL REFERENCES turns,
    content_id text NOT NULL, content_version text NOT NULL, snapshot_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('hint','explanation','example')),
    family_id text, source_group text, lineage_ids text[] NOT NULL,
    PRIMARY KEY(turn_id,content_id,content_version)
);
CREATE TABLE session_reports (
    session_id uuid PRIMARY KEY REFERENCES sessions,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
