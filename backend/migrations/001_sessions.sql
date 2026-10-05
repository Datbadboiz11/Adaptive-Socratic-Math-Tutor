CREATE TABLE profiles (
    student_id text PRIMARY KEY,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE demo_tokens (
    token_hash text PRIMARY KEY,
    student_id text NOT NULL REFERENCES profiles,
    expires_at timestamptz NOT NULL
);
CREATE TABLE topics (topic_id text PRIMARY KEY, title text NOT NULL);
CREATE TABLE problems (
    problem_id text NOT NULL,
    content_version text NOT NULL,
    topic_id text NOT NULL REFERENCES topics,
    family_id text NOT NULL,
    source_group text NOT NULL,
    primary_skill_id text NOT NULL,
    review_status text NOT NULL CHECK (review_status IN ('draft','machine_checked','human_approved')),
    public_payload jsonb NOT NULL,
    private_payload jsonb NOT NULL,
    content_hash text NOT NULL,
    PRIMARY KEY (problem_id, content_version)
);
CREATE TABLE sessions (
    session_id uuid PRIMARY KEY,
    student_id text NOT NULL REFERENCES profiles,
    topic_id text NOT NULL REFERENCES topics,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','completed')),
    state_version integer NOT NULL DEFAULT 1 CHECK (state_version >= 1),
    current_opportunity_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (session_id, student_id)
);
CREATE TABLE opportunities (
    opportunity_id uuid PRIMARY KEY,
    session_id uuid NOT NULL,
    student_id text NOT NULL,
    problem_id text NOT NULL,
    content_version text NOT NULL,
    target_skill_id text NOT NULL,
    relation text NOT NULL CHECK (relation IN ('initial','near_practice','cross_family','repeat')),
    related_problem_id text,
    assistance_level integer NOT NULL DEFAULT 0 CHECK (assistance_level BETWEEN 0 AND 3),
    draft text NOT NULL DEFAULT '' CHECK (length(draft) <= 2000),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    protocol_version text NOT NULL DEFAULT 'g2-v1',
    outcome text CHECK (outcome IN ('independent_correct','assisted_correct')),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (session_id, student_id) REFERENCES sessions(session_id, student_id),
    FOREIGN KEY (problem_id, content_version) REFERENCES problems,
    UNIQUE (session_id, ordinal),
    UNIQUE (opportunity_id, session_id),
    UNIQUE (opportunity_id, student_id, target_skill_id)
);
ALTER TABLE sessions ADD CONSTRAINT current_opportunity_belongs_to_session
    FOREIGN KEY (current_opportunity_id, session_id)
    REFERENCES opportunities(opportunity_id, session_id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE turns (
    turn_id uuid PRIMARY KEY,
    session_id uuid NOT NULL,
    opportunity_id uuid NOT NULL,
    request_id uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('submit','request_hint')),
    steps jsonb NOT NULL,
    assessment jsonb NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (opportunity_id, session_id) REFERENCES opportunities(opportunity_id, session_id),
    UNIQUE (session_id, request_id),
    UNIQUE (turn_id, opportunity_id)
);
CREATE TABLE observations (
    observation_id uuid PRIMARY KEY,
    student_id text NOT NULL,
    opportunity_id uuid NOT NULL,
    skill_id text NOT NULL,
    turn_id uuid NOT NULL REFERENCES turns,
    correct boolean NOT NULL,
    prediction_before double precision NOT NULL CHECK (prediction_before BETWEEN 0 AND 1),
    mastery_before double precision NOT NULL CHECK (mastery_before BETWEEN 0 AND 1),
    mastery_after double precision NOT NULL CHECK (mastery_after BETWEEN 0 AND 1),
    parameter_version text NOT NULL,
    protocol_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (opportunity_id, student_id, skill_id)
        REFERENCES opportunities(opportunity_id, student_id, target_skill_id),
    FOREIGN KEY (turn_id, opportunity_id) REFERENCES turns(turn_id, opportunity_id),
    UNIQUE (student_id, opportunity_id, skill_id)
);
CREATE TABLE mastery_history (
    observation_id uuid PRIMARY KEY REFERENCES observations,
    state_before jsonb NOT NULL,
    state_after jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE decisions (
    decision_id uuid PRIMARY KEY,
    turn_id uuid NOT NULL UNIQUE REFERENCES turns,
    action text NOT NULL,
    reason text NOT NULL,
    pipeline_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE requests (
    student_id text NOT NULL REFERENCES profiles,
    scope text NOT NULL,
    request_id uuid NOT NULL,
    payload_hash text NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (student_id, scope, request_id)
);
CREATE INDEX sessions_owner_idx ON sessions(student_id, updated_at DESC);
CREATE INDEX turns_session_idx ON turns(session_id, created_at);
CREATE INDEX opportunities_problem_idx ON opportunities(student_id, problem_id);
