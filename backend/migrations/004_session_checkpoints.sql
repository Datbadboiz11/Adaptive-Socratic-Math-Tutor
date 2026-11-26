CREATE TABLE session_checkpoints (
    session_id uuid PRIMARY KEY REFERENCES sessions(session_id),
    state_version integer NOT NULL CHECK (state_version >= 1),
    snapshot jsonb NOT NULL,
    saved_at timestamptz NOT NULL DEFAULT now()
);
