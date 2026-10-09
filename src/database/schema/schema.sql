-- Initial schema for the Data Aggregation Pipeline (Epic #4) and
-- Instructor Analytics Dashboard (Epic #5)
-- No personally identifying information is stored: `session_id` is a
-- randomly generated UUID per browser session, not tied to student
-- identity, per the anonymisation requirement in #4's Data
-- Aggregation Pipeline feature

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
    submission_id       BIGINT NOT NULL REFERENCES submissions (id) ON DELETE CASCADE,  -- cascade: deleting a submission removes its errors (#23)
    error_type          TEXT NOT NULL,      -- e.g. "SyntaxError", "IndexError"
    message             TEXT,               -- the actual Python error message, e.g. "list index out of range"
    concept             TEXT,               -- higher-level grouping, see #5 Conceptual Struggle Tracking
    line_number         INTEGER,
    code_snippet        TEXT,               -- the failing source line itself
    hint_stage_reached  SMALLINT NOT NULL DEFAULT 1,
    vague_attempts_this_stage SMALLINT NOT NULL DEFAULT 0,
    pending_resource_concept  TEXT,                          -- concept key (e.g. "dictionaries") while a resource gate is open, NULL otherwise
    resource_offered          BOOLEAN NOT NULL DEFAULT false, -- set once a resource has been offered for this error; never reset
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hint_events (
    id            BIGSERIAL PRIMARY KEY,
    error_log_id  BIGINT NOT NULL REFERENCES error_logs (id) ON DELETE CASCADE,  -- cascade: deleting an error removes its hints (#23)
    stage         SMALLINT NOT NULL,   -- 1-4, matches the staged hint UI (#10, #12)
    hint_text     TEXT NOT NULL,
    shown_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_error_logs_error_type ON error_logs (error_type);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at ON error_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_type_submission
    ON error_logs (created_at, error_type, submission_id);
CREATE INDEX IF NOT EXISTS idx_hint_events_error_log_id ON hint_events (error_log_id);
CREATE INDEX IF NOT EXISTS idx_error_logs_submission_id ON error_logs (submission_id);  -- speeds up cascade deletes (#23)
CREATE INDEX IF NOT EXISTS idx_submissions_course ON submissions (course);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions (created_at);

ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE error_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE hint_events ENABLE ROW LEVEL SECURITY;

-- When student data is deleted (on request or by the scheduled purge),
-- everything is removed except the aggregate counts the instructor
-- dashboard needs. Those counts are put into the two tables below
-- first. They hold no session IDs, no code, and no submission links,
-- and error messages are cleaned so student variable names are not kept.

CREATE TABLE IF NOT EXISTS submission_daily_counts (
    day               DATE NOT NULL,      -- UTC day the submissions were made
    course            TEXT,
    submission_count  INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT submission_daily_counts_key
        UNIQUE NULLS NOT DISTINCT (day, course)
);

CREATE TABLE IF NOT EXISTS error_daily_counts (
    day          DATE NOT NULL,           -- UTC day the errors were logged
    course       TEXT,
    error_type   TEXT,
    message      TEXT,                    -- cleaned with normalise_error_message()
    outcome      TEXT NOT NULL
        CHECK (outcome IN ('resolved', 'attempted', 'untried', 'other')),
    error_count  INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT error_daily_counts_key
        UNIQUE NULLS NOT DISTINCT (day, course, error_type, message, outcome)
);

ALTER TABLE submission_daily_counts ENABLE ROW LEVEL SECURITY;
ALTER TABLE error_daily_counts ENABLE ROW LEVEL SECURITY;


-- Replaces quoted text in an error message with '...' so student
-- variable names, strings and filenames are not kept. Built-in type
-- names, common built-in functions and brackets are kept, since they
-- cannot identify anyone and are useful to instructors.
-- e.g. name 'john_total' is not defined becomes  name '...' is not defined
CREATE OR REPLACE FUNCTION normalise_error_message(msg TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  WITH keep AS (
    SELECT '(int|str|float|bool|list|dict|tuple|set|NoneType|bytes|complex|range|function|module|type|object|True|False|None|print|input|len|help|abs|id|sum|min|max|round|sorted|open|isinstance|enumerate|zip|map|filter|\(|\)|\[|\]|\{|\})' AS names
  )
  SELECT
    regexp_replace(              -- 6. restore protected "names"
    regexp_replace(              -- 5. restore protected 'names'
    regexp_replace(              -- 4. clean all other "..."
    regexp_replace(              -- 3. clean all other '...'
    regexp_replace(              -- 2. protect "int" etc.
    regexp_replace(              -- 1. protect 'int' etc.
      coalesce(msg, ''),
      '''' || names || '''', '«\1»', 'g'),
      '"' || names || '"', '‹\1›', 'g'),
      '''[^'']*''', '''...''', 'g'),
      '"[^"]*"', '"..."', 'g'),
      '«([^»]*)»', '''\1''', 'g'),
      '‹([^›]*)›', '"\1"', 'g')
  FROM keep;
$$;


-- Gathers the given submissions into the daily count tables, then deletes
-- them. The cascade removes their error_logs and hint_events. Runs as
-- one transaction, so counts and deletions can't get out of sync.
-- Used by the scheduled purge. Returns the number of submissions deleted.
CREATE OR REPLACE FUNCTION rollup_and_delete_submissions(target_ids BIGINT[])
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  -- Lock the rows so two deletions running at once can't count the same data twice
  PERFORM 1 FROM submissions WHERE id = ANY(target_ids) FOR UPDATE;

  -- Add the submissions to the daily submission counts
  INSERT INTO submission_daily_counts (day, course, submission_count)
  SELECT (s.created_at AT TIME ZONE 'UTC')::date, s.course, count(*)
  FROM submissions s
  WHERE s.id = ANY(target_ids)
  GROUP BY 1, 2
  ON CONFLICT ON CONSTRAINT submission_daily_counts_key
  DO UPDATE SET submission_count =
    submission_daily_counts.submission_count + excluded.submission_count;

  -- Add their errors to the daily error counts, with messages cleaned
  INSERT INTO error_daily_counts (day, course, error_type, message, outcome, error_count)
  SELECT
    (el.created_at AT TIME ZONE 'UTC')::date,
    s.course,
    el.error_type,
    nullif(trim(normalise_error_message(el.message)), ''),
    CASE
      WHEN el.resolved_at IS NOT NULL THEN 'resolved'
      WHEN el.hint_stage_reached > 1 THEN 'attempted'
      WHEN el.hint_stage_reached = 1 THEN 'untried'
      ELSE 'other'
    END,
    count(*)
  FROM error_logs el
  JOIN submissions s ON s.id = el.submission_id
  WHERE s.id = ANY(target_ids)
  GROUP BY 1, 2, 3, 4, 5
  ON CONFLICT ON CONSTRAINT error_daily_counts_key
  DO UPDATE SET error_count =
    error_daily_counts.error_count + excluded.error_count;

  -- Delete the submissions (cascade removes error_logs and hint_events)
  DELETE FROM submissions WHERE id = ANY(target_ids);
  GET DIAGNOSTICS deleted_count = ROW_COUNT;

  RETURN deleted_count;
END;
$$;


-- Deletes everything for one session. Used by the student deletion
-- request endpoint. Returns the number of submissions deleted.
CREATE OR REPLACE FUNCTION delete_session_data(p_session_id UUID)
RETURNS INTEGER
LANGUAGE sql
SET search_path = public
AS $$
  SELECT rollup_and_delete_submissions(
    array(SELECT id FROM submissions WHERE session_id = p_session_id)
  );
$$;

-- Dashboard reads from these views, which combine live data with the
-- daily count tables, so numbers stay the same after deletion.
-- security_invoker makes the views follow the tables RLS rules.
CREATE OR REPLACE VIEW submission_counts
WITH (security_invoker = true) AS
  SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
         course,
         count(*)::bigint AS submission_count
  FROM submissions
  GROUP BY 1, 2
  UNION ALL
  SELECT day, course, submission_count::bigint
  FROM submission_daily_counts;

CREATE OR REPLACE VIEW error_counts
WITH (security_invoker = true) AS
  SELECT (el.created_at AT TIME ZONE 'UTC')::date AS day,
         s.course,
         el.error_type,
         nullif(trim(normalise_error_message(el.message)), '') AS message,
         CASE
           WHEN el.resolved_at IS NOT NULL THEN 'resolved'
           WHEN el.hint_stage_reached > 1 THEN 'attempted'
           WHEN el.hint_stage_reached = 1 THEN 'untried'
           ELSE 'other'
         END AS outcome,
         count(*)::bigint AS error_count
  FROM error_logs el
  JOIN submissions s ON s.id = el.submission_id
  GROUP BY 1, 2, 3, 4, 5
  UNION ALL
  SELECT day, course, error_type, message, outcome, error_count::bigint
  FROM error_daily_counts;