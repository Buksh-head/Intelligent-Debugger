-- Synthetic example rows for local development only. No real student
-- data. Session IDs are placeholder UUIDs.

INSERT INTO submissions (session_id, code, code_hash, expected_behaviour) VALUES
    ('11111111-1111-1111-1111-111111111111', E'nums = [1, 2, 3]\nprint(nums[5])', 'sha256:example-hash-1', 'Print the 5th item in the list'),
    ('22222222-2222-2222-2222-222222222222', E'def broken(:\n    pass', 'sha256:example-hash-2', 'Define a function that adds two numbers');

INSERT INTO error_logs (submission_id, error_type, concept, line_number, code_snippet, hint_stage_reached) VALUES
    (1, 'IndexError', 'off-by-one', 4, 'print(nums[5])', 2),
    (2, 'SyntaxError', 'syntax', 1, 'def broken(:', 1);

INSERT INTO hint_events (error_log_id, stage, hint_text) VALUES
    (1, 1, 'Check the size of your list versus the index you are using.'),
    (1, 2, 'Lists are zero-indexed - the last valid index is one less than the length.'),
    (2, 1, 'Look closely at the function definition line - something is unbalanced.');
