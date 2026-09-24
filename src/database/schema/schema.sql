-- Initial schema for the Data Aggregation Pipeline (Epic #4) and
-- Instructor Analytics Dashboard (Epic #5).
--
-- No personally identifying information is stored: `session_id` is a
-- randomly generated UUID per browser session, not tied to student
-- identity, per the anonymisation requirement in #4's Data
-- Aggregation Pipeline feature.

CREATE TABLE IF NOT EXISTS submissions (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID NOT NULL,
    code                TEXT NOT NULL,        -- full submitted code, kept per-submission so history can be shown later
    code_hash           TEXT NOT NULL,        -- hash of submitted code, used to detect resubmission (see #11)
    expected_behaviour  TEXT,                 -- student's own description of what the code should do
    course              TEXT,                 -- course code selected by the student
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_submissions_session_id ON submissions (session_id);

CREATE TABLE IF NOT EXISTS error_logs (
    id                  BIGSERIAL PRIMARY KEY,
    submission_id       BIGINT NOT NULL REFERENCES submissions (id),
    error_type          TEXT NOT NULL,      -- e.g. "SyntaxError", "IndexError"
    message             TEXT,               -- the actual Python error message, e.g. "list index out of range"
    concept             TEXT,               -- higher-level grouping, see #5 Conceptual Struggle Tracking
    line_number         INTEGER,
    code_snippet        TEXT,               -- the failing source line itself
    hint_stage_reached  SMALLINT NOT NULL DEFAULT 1,
    vague_attempts_this_stage SMALLINT NOT NULL DEFAULT 0,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hint_events (
    id            BIGSERIAL PRIMARY KEY,
    error_log_id  BIGINT NOT NULL REFERENCES error_logs (id),
    stage         SMALLINT NOT NULL,   -- 1-4, matches the staged hint UI (#10, #12)
    hint_text     TEXT NOT NULL,
    shown_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_error_logs_error_type ON error_logs (error_type);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON error_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_hint_events_error_log_id ON hint_events (error_log_id);
