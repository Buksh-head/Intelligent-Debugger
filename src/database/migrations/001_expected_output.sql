-- Added for the logic-error feature (the Expected behaviour tab).
-- Run once in the Supabase SQL Editor, before deploying the backend that uses it.
--
-- The output the student said they expect their program to print. Kept per
-- session, like the editor code, so the Expected behaviour tab and any hint
-- about wrong output come back when the student continues the session.
-- NULL when the student hasn't typed one.
ALTER TABLE student_sessions ADD COLUMN IF NOT EXISTS expected_output TEXT;
