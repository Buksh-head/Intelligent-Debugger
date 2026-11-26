# Backend: hints, answers and saved sessions

The API behind Error Guide, a debugger for first-year Python students. When a
student's program crashes, times out, or prints something other than what
they expected, the tool shows **one leading question** that points at the
cause without giving the answer (stage 1). The student can answer it in their
own words, and the tool branches on that reply (stage 2): a narrower or
different question if they're not there yet, or a short answer once they've
found it. A student who is stuck can instead ask for the whole answer
(**Show me the answer**), which comes with the misconception the team's
classifier detected and why.

What the app does for students and instructors, and how to deploy it, is in
the [top-level README](../../README.md). This page covers how the backend
works.

> `word.isvowel()` → AttributeError
> **"On line 3 you call isvowel() on a string. Is isvowel actually one of the methods Python strings have?"**

## How it works

```
student code ─► runner.py ─► analysis.py ─► hints.py ──────► guardrails.py ─► student
                (Piston or    (traceback +    one structured   reject leaks,     sees one
                 subprocess)  verified facts) call to Claude   retry once,       question
                                              or Gemini        else fallback.py
```

1. **runner.py** runs the code in a fresh `python -I` process in an empty temp
   dir with a timeout and CPU/memory limits.
2. **analysis.py** (no AI) parses the traceback (last exception in a chain,
   last line in the student's file), and computes *verified facts* the model
   can rely on, e.g. "isvowel is not a method of str", "total is assigned on
   line 6, after it is used on line 3". It also collects **giveaways**: the
   real names that would be the answer (Python's own "Did you mean" suggestion,
   close matches from `dir(str)`, similar defined variable names).
3. **explain.py** (no AI) rewrites Python's message in plain English for the
   error box, e.g. `TypeError: type NoneType doesn't define __round__ method`
   becomes "round() was not given a number. On line 8, you call round() on
   None (which means "no value"). round() only works on numbers." It covers
   the errors first-years hit most, with a general sentence for anything
   else. It says only what Python said, never why or how to fix it. For
   runtime errors it drops Python's "Did you mean" suggestions (they are the
   answer). For syntax errors it follows Python's suggestion instead, so
   "invalid syntax. Perhaps you forgot a comma?" becomes "Python thinks a
   comma (,) is missing", and `if x = 5:` gets a message about `=` vs `==`.
4. **hints.py** makes one model call through **providers.py**: Claude by
   default (`claude-opus-5-5`, adaptive thinking, effort `medium`, both
   adjustable, see [Where the time goes](#where-the-time-goes)), or Gemini
   with `DEBUGGER_PROVIDER=gemini` (`gemini-3.5-flash`, free tier). Both use
   the same prompt and the same structured output. The model first states, privately, the
   root cause, the cause line (often not the line Python stopped at), the
   student's misconception and its own list of giveaway words, then writes the
   question. Only the question reaches the student; the rest is kept for
   teachers and for later stages.
5. **guardrails.py** checks every question: exactly one question, ≤ 45 words,
   plain text, anchored to a line or identifier from the student's code, no
   "you should / instead / did you mean / replace", and none of the giveaway
   words (from the analysis *and* the model). A failing question is sent back
   once with the reasons; if it fails again, or the API is unavailable,
   **fallback.py** gives a safe rule-based question.
6. The Output tab shows Python's message exactly as Python wrote it, including
   any "Did you mean: 'islower'?" suggestion. Anything on screen there may be
   quoted by a hint without tripping the guardrails (`visible_text`).

The prompt is in `debugger/prompts.py` (`PROMPT_VERSION = "stage1-v1"`).

## Stage 2: branching on the student's reply

`debugger/followup.py`. The student's reply, the questions so far and the same
verified facts go to the model, which first assesses the latest reply and then
branches:

| Assessment | Example reply (to the isvowel question) | Response |
| --- | --- | --- |
| `found_it` | "isvowel isn't a real string method" | **Answer**: confirms, explains why it causes the error, names the line, no corrected code |
| `partly` | "something on line 2 is wrong" | **Question** that narrows in on the missing part |
| `wrong_idea` | "the word variable is empty" | **Question** from a different angle that tests their idea against the evidence |
| `unsure` / `off_topic` | "idk", "just tell me" | **Question** that is a smaller, more concrete step (one word, one value to print) |

The prompt (`FOLLOWUP_SYSTEM_PROMPT`) asks for the voice of a warm tutor sitting
next to the student: respond to what they actually said, in their words, with
contractions and honest, specific encouragement, reassure them when they're
stuck or frustrated, and never open two messages the same way. It includes
robotic-vs-human examples. Each follow-up escalates (1: point more precisely,
2: a small experiment to run, last: the answer), and the user message lists
what was already said so the model doesn't circle back; reworded repeats are
also caught by `repeats_earlier_question`.

The student can reply to each follow-up question. After 3 follow-up questions
(`MAX_FOLLOWUP_QUESTIONS`) the tool answers whatever the reply, so nobody goes
round in circles; that last answer may name the fix, but still not as code.

Guardrails (`guardrails.py`): questions get the stage 1 checks plus "not a
repeat of an earlier question"; answers get `check_answer` (no Markdown, no
"change X to", at most 60 words, anchored to the code). Giveaway names are
blocked unless the student wrote that exact word themselves, so "it should be
True" unlocks True but "true is a boolean" does not. The code also checks the
branch matches the assessment (found_it must be an answer, the others
questions). One retry with the checker's reasons, then a rule-based response
(`followup_fallback` in `fallback.py`): a more concrete question per error
type, or an answer when the reply names the fix or it is the last turn.

## Logic errors: the program runs, but prints the wrong thing

`debugger/logic.py`. When a run finishes without crashing, the student can type
the output they expected. `POST /api/check-output` compares it with what the
program printed (line by line, ignoring trailing spaces, blank lines at either
end and the text of `input()` prompts) and says where they first differ, with
no model call.

When they differ, **Give me a hint** sends `expected` with the usual stage 1
and stage 2 requests. `analyse_logic` then builds a report like a crash
report, with kind `logic`:

- **Verified facts** from the code and both outputs: the first line that
  differs, one line missing or extra, numbers off by one, which function calls
  itself and what it returns when it stops, what each `range()` and `while`
  goes through, how Python groups `a + b / 2`, `//` dropping decimals, a
  function with no `return` value.
- **A first guess at the kind of mistake** from those clues: `off_by_one`,
  `recursion_base_case`, `calculation`, `missing_return` or `other`. The model
  (`LOGIC_SYSTEM_PROMPT`, kept short for Haiku) makes the final call and
  returns it as `category`, shown to the student as a label on the hint.

The question follows the same rules and checks as for crashes, plus two more
for logic errors, where the fix is usually tiny: it may not write code that
isn't in the student's program (`range(1, 6)`, `i <= 10`; `print(...)`
experiments are fine), and short giveaways like a range limit or an operator
are checked too. Follow-ups reuse stage 2 with the expected and actual output
in place of the traceback. Without a model, `logic_fallback_question` and
`logic_followup_fallback` ask a question per kind of mistake.

`python -m evals.run_logic_eval` runs the 27 sample programs in
`evals/logic_cases.py` through the chosen model and checks the category and line.

## Socratic mode: "Show me the answer"

Next to "Give me a hint" (and under the hints, as "Still stuck?"), the student
can ask for the whole answer. `POST /api/answer` takes the same run as
`/api/hints/stage1` and returns what went wrong (`diagnosis`) and how to fix it
(`fix`, which may include code), ported from the team version's Socratic mode.

- `debugger/answer.py` asks the chosen provider for `reasoning`, `diagnosis`
  and `fix` with the team's prompt. Giving the answer is the point, so, as in
  the original, none of the hint guardrails run on it. The hints and
  follow-ups are still checked exactly as before.
- Without a model it falls back to the plain-English explanation of the error
  and, when Python gave one, its "Did you mean" suggestion as the fix.
- `debugger/explainability/` is the team's misconception classifier (logistic
  regression on AST features and the error message, trained on the 266
  synthetic programs in `data/misconceptions.jsonl`, 81% held-out accuracy in
  `artifacts/eval_report.json`). Each answer comes with the misconception it
  picks and what in the code pointed there, computed as linear SHAP with numpy.
  The student sees them under "How did it work this out?". Logic errors only
  get the model's reasoning, since the classifier was trained on crashes and
  timeouts.
- LIME and DiCE are offline cross-checks and never load in the app. Install
  `requirements-explain.txt` to run their tests (skipped otherwise).
  Retrain with `python -m debugger.explainability.trainer`, which also rewrites
  the eval report; scikit-learn stays pinned to 1.9 so the saved model loads.

## Run it

The full stack (this API, the Error Guide frontend and the Piston sandbox) is
described in the [top-level README](../../README.md). To run just this API:

```bash
pip install -r requirements.txt           # includes scikit-learn, pandas and numpy for the classifier
export ANTHROPIC_API_KEY=...          # without it, every hint comes from the rule-based fallback
# or: export DEBUGGER_PROVIDER=gemini GEMINI_API_KEY=...   (free tier)
export PISTON_URL=http://localhost:2000   # leave unset to run code in a local subprocess instead
export DATABASE_URL=postgresql://...      # optional: Supabase Postgres, for saved sessions and the dashboard
export SUPABASE_URL=https://<ref>.supabase.co   # to check logins (needed with DATABASE_URL)
uvicorn app.main:app --reload --port 8000
```

Routes (`app/main.py`):

| Route | Does |
| --- | --- |
| `GET /health` | `{"status": "ok"}` |
| `POST /api/execute` | `{code, stdin?, language?, course?, session_id?, expected?}` → runs it in Piston, returns stdout, stderr and the parsed error: Python's message (suggestions removed) plus `friendly_title` / `friendly_message` in plain English. With a database, also `submission_id` and `error_id` |
| `POST /api/hints/stage1` | `{code, stdin, execution, expected?, session_id?, error_id?}` (the run the student already has; `expected` for a logic error) → `{question, error_type, error_line, cause_line, source, category?, category_label?}` |
| `POST /api/hints/followup` | `{code, stdin, execution, turns: [{question, reply}, ...], expected?, session_id?, error_id?}` (stage 1 question first, last reply is the new one) → `{kind: "question" \| "answer", text, assessment, cause_line, turn, final, source}` |
| `POST /api/answer` | Same body as `/api/hints/stage1` → `{diagnosis, fix, error_type, error_line, source, explanation?}`, where `explanation` is `{reasoning, misconception, attributions}`. 422 if the run has no error |
| `POST /api/check-output` | `{code, stdout, expected, session_id?, submission_id?}` → `{matches, title, message, first_diff, expected_line, actual_line, error_id}` |
| `/api/student/me`, `/api/student/sessions[/{id}[/messages\|/state]]` | Saved sessions, student login needed (`app/student_sessions.py`): create, list, load, rename, save the hint conversation, save the code / run / expected output, delete |
| `GET /api/analytics/cohort`, `GET /api/analytics/insights/{error_type}` | Instructor dashboard, instructor login needed (`app/dashboard.py`) |

## Database: saved sessions and the instructor dashboard

Optional. With `DATABASE_URL` (the Supabase Postgres connection string) the
API saves what the team's version saved, in the team's tables
(`src/database/schema/`), plus one column (`src/database/migrations/`):

| What | Where |
| --- | --- |
| Every run | `submissions` (code, course, session, the expected output if typed) |
| A crash or timeout | `error_logs` (error type, Python's message, line). A later run that finishes marks it resolved |
| Output that differs from the expected output | `error_logs` with `error_type = 'LogicError'`, once per run. The hint adds the kind of mistake (`concept`, e.g. `off_by_one`, and `message`, e.g. "Looks like an off-by-one mistake"). Output that matches marks it resolved |
| Each hint shown | `hint_events` (stage 1 = the first question, stage n + 1 = the follow-up to reply n). `error_logs.hint_stage_reached` goes up, so the dashboard counts a replied-to error as "attempted" |
| The student's session | `student_sessions` (code, last run with its input, `expected_output`), keyed by the account email as before |
| The hint conversation | `chat_messages`, one row per message: `{kind: "hint"}`, `{kind: "reply"}`, `{kind: "followup"}`, `{kind: "answer"}` (Show me the answer, with its explanation), and an `event` row `{kind: "run"}` when a new run starts a new conversation. Continuing a session restores the conversation about the last run |
| Deleted sessions | Rolled up into `submission_daily_counts` / `error_daily_counts` by the team's `delete_session_data()`, so the dashboard keeps its numbers |

Logins are Supabase access tokens, checked against the project's public keys
(`SUPABASE_URL/auth/v1/.well-known/jwks.json`), or `SUPABASE_JWT_SECRET` for
a project still on the legacy HS256 secret. The role comes from
`public.profiles`. A hint or output check is only saved under an error of the
same session (the session ID is a random UUID the browser holds). Saving never
gets in the way: if the database is down, the run and the hint still work and
the failure is logged.

The dashboard's AI insight is written by the hint model (Claude or Gemini),
from counts and cleaned error messages only, never code.

## Where the time goes

Each hint request logs one line saying where its wait went, plus one line per
model call (look for them in the backend's console or container log):

```
INFO:     debugger.providers: model call claude:claude-haiku-5-5 HintDraft: 4.31 s, input 1520 tokens (1180 from cache), output 1210 tokens (answer ~140, thinking ~1070), stop end_turn
INFO:     debugger.api: stage1 timing: 4.33 s total = model 4.31 s over 1 call(s) [4.31] + checks 0.02 s; source model
```

* **model** is the time spent waiting for Claude or Gemini. Two calls mean
  the guardrails rejected the first draft and the model was asked again.
* **thinking** is the share of the output tokens the model spent reasoning
  before it wrote the answer (an estimate for Claude: output tokens minus the
  visible answer at about 4 characters a token).
* **checks** is everything else in the request: reading the error, the
  guardrails, and building the response.

Saving the hint for the dashboard happens after the response is sent (under
uvicorn, as in the Docker setup), so the
student never waits for the database; it logs its own line ("saved hint stage
1 in 0.42 s (after the response)"). The model's HTTP client is reused between
requests, so a hint doesn't pay to open a new connection to the provider.

Most of the wait is the model thinking before it answers. Two settings trade
some of that thinking for speed: `DEBUGGER_EFFORT` (`low` | `medium` | `high`)
and `DEBUGGER_THINKING` (`on` | `off`). Both can make the hints worse, so
compare them on the eval cases first; this times each setting side by side and
runs the eval's checks on every hint and follow-up:

```bash
DEBUGGER_MODEL=claude-haiku-5-5 python -m evals.compare_speed                     # medium, low, low:off
DEBUGGER_MODEL=claude-haiku-5-5 python -m evals.compare_speed --settings medium,low
```

It prints a table (hints passed, median and slowest seconds, redrafts) and
writes every question side by side to `evals/speed-<model>.md`. Read those
before switching: the checks catch leaks, not whether a question still helps.

Every API request also logs its own time, e.g. `GET /api/student/sessions 200
in 0.21 s`. Most of the time in the session routes and the Run button is
round trips to the database (with Supabase, tens to hundreds of milliseconds
each, depending on its region), so these keep them few: the login's role is
remembered for 5 minutes, reads skip the BEGIN / ROLLBACK, and a run is saved
in a single statement.

## Tests and eval

```bash
python -m pytest -q ../../tests/backend   # offline, 312 tests: analysis, guardrails, retry/fallback flow, logic errors, answers, classifier, API routes (fake model, fake Piston)
# also the database tests: a scratch Postgres 15+ database, which they wipe (never Supabase)
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/debugger_test python -m pytest -q ../../tests/backend
python -m evals.run_eval                  # live: 18 common first-year bugs through the chosen provider, needs its key
python -m evals.run_logic_eval            # live: 27 wrong-output programs, checks the kind of mistake and the line
python -m evals.compare_speed             # live: the eval's checks and timings for each effort / thinking setting
pip install -r requirements-explain.txt   # then the SHAP, LIME and DiCE cross-check tests run too (skipped otherwise)
```

`evals/cases.py` holds the 18 cases (isvowel, typos, input() returning str,
off-by-one, list.sort() returning None, missing return, `=` in an if, missing
colon, indentation, KeyError case, empty average, UnboundLocalError,
int("3.50"), calling a list, math.sqroot, missing base case, infinite loop),
each with the real cause line and the words a hint must not say. The eval
checks those automatically; read the questions too, because the checks catch
leaks, not whether a question is genuinely helpful.

## Not done yet

- Logic errors are only found when the student types the output they
  expected; there is no test-case or instructor-supplied expected output yet.
- The local subprocess runner (used when `PISTON_URL` is unset) is not a
  security sandbox; deployments use Piston.
- **Show me the answer** is available from the start, with no minimum number
  of hints first, and is not checked by any guardrail.
- The misconception classifier learned from 266 synthetic programs the team
  wrote (see [its data README](debugger/explainability/data/README.md)), so
  its 81% accuracy says how well it reproduces those examples, not how it does
  on real students' code.
