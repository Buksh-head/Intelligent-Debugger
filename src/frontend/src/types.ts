// Types mirroring the backend's API schemas (backend/app/main.py).
// Keep these in sync if that file changes.

// Execution and hint types describe the feedback exchanged while a student
// runs code and works through the debugging assistant.
export interface ExecutionError {
  error_type: string;
  message: string; // Python's own message, shown in the Output panel
  line_number: number | null;
  code_snippet: string | null;
  // The same error in plain English for beginners, shown in the hint box.
  // Optional so results saved before this existed still display.
  friendly_title?: string;
  friendly_message?: string;
}

export interface ExecutionResponse {
  stdout: string;
  stderr: string;
  exit_code: number | null;
  status: string | null;
  timed_out: boolean;
  error: ExecutionError | null;
  // The saved error and run, when the backend has a database. Sent back with
  // the hint and output check requests so they are recorded for the dashboard.
  error_id: number | null;
  submission_id?: number | null;
}

// A run as saved with the session: the result plus the input it ran with, so
// follow-up hints after continuing get the same input.
export type SavedExecution = ExecutionResponse & { stdin?: string };

// Ties a hint or output check to the saved session and error.
export interface SavedErrorRef {
  session_id?: string;
  error_id?: number | null;
}

// The stage 1 hint from /api/hints/stage1: one leading question about the
// error in a run. cause_line is where the mistake is, which can differ from
// the line Python stopped at (error_line).
export interface Stage1Hint {
  question: string;
  error_type: string | null;
  error_line: number | null;
  cause_line: number | null;
  source: "model" | "fallback";
  // Logic errors only: the kind of mistake ("off_by_one", "recursion_base_case",
  // "calculation", "missing_return" or "other") and its label for the student,
  // e.g. "an off-by-one mistake".
  category?: string | null;
  category_label?: string | null;
}

// /api/check-output: a finished run's output against what the student expected.
// first_diff is the 1-based output line where they first differ.
export interface OutputCheck {
  matches: boolean;
  title: string;
  message: string;
  first_diff: number | null;
  expected_line: string | null;
  actual_line: string | null;
  // The LogicError saved for a difference, when the run was saved.
  error_id?: number | null;
}

// Stage 2: one question the student was asked and what they replied.
export interface HintTurn {
  question: string;
  reply: string;
}

// Stage 2: the tool's response to the student's latest reply. A "question"
// can be replied to again; an "answer" ends the hints for this run.
export interface FollowUpHint {
  kind: "question" | "answer";
  text: string;
  assessment:
    | "found_it"
    | "partly"
    | "wrong_idea"
    | "unsure"
    | "off_topic"
    | "unknown";
  cause_line: number | null;
  turn: number;
  final: boolean;
  source: "model" | "fallback";
}

// Socratic mode, /api/answer: the whole answer in one turn. diagnosis is what
// the code does and why it fails; fix is the change that resolves it and may
// contain code. explanation says how it was worked out, or is null.
export interface SocraticAnswer {
  diagnosis: string | null;
  fix: string | null;
  error_type: string | null;
  error_line: number | null;
  source: "model" | "fallback";
  explanation: Explanation | null;
}

// One thing that pointed the misconception classifier at its choice.
export interface Attribution {
  feature: string;
  label: string; // the only part a student sees
  weight: number;
}

// How an answer was reached: the model's reasoning, the misconception the
// classifier picked (e.g. "off-by-one") and what in the code pointed there,
// strongest first (SHAP). Any field may be missing.
export interface Explanation {
  reasoning: string | null;
  misconception: string | null;
  confidence: number | null;
  attributions: Attribution[] | null;
  counterfactual_question: string | null;
}

// One message in the Student View chat.
export type ChatMessage = {
  role: "student" | "assistant" | "event"; // 'event' marks a resubmission within the chat
  text: string;
  stage?: number;
  resourceUrl?: string | null; // link from the curated list, if this message offers one
  resourceLabel?: string | null; // the link's title
  gated?: boolean; // true while the student still owes the check answer
};

// A message of the hint conversation as saved to the student's account.
// "hint": the stage 1 question (with the output check, for a logic error);
// "reply": what the student answered; "followup": the response to it;
// "answer": the Socratic answer (with the output check, for a logic error);
// "run": an event marking a new run or check, which starts a new conversation.
export type SavedHintBody =
  | {
      kind: "hint";
      text: string;
      hint: Stage1Hint;
      check?: OutputCheck | null;
      expected?: string | null;
    }
  | { kind: "reply"; text: string }
  | { kind: "followup"; text: string; followup: FollowUpHint }
  | {
      kind: "answer";
      text: string;
      answer: SocraticAnswer;
      check?: OutputCheck | null;
      expected?: string | null;
    }
  | { kind: "run"; text: string };

// One saved message. Sessions saved by the team's chat version have bodies
// in the ChatMessage shape instead (no kind); those are ignored on restore.
export interface ChatMessageRecord {
  position: number;
  role: ChatMessage["role"];
  body: SavedHintBody | Omit<ChatMessage, "role">;
}

// One row of the student's session history.
export interface StudentSessionSummary {
  id: string;
  course: string | null;
  language: string | null;
  title: string | null; // null until the student renames the session
  latest_error_type: string | null;
  latest_error_message: string | null;
  has_unresolved_error: boolean;
  last_run_passed: boolean | null; // null until the code has been run
  last_activity: string; // ISO timestamp
}

// A saved session, with what's needed to continue it.
export interface StudentSessionDetail {
  id: string;
  course: string | null;
  language: string | null;
  code: string | null;
  last_execution: SavedExecution | null;
  expected_output?: string | null;
  messages: ChatMessageRecord[];
}

export interface AnalyticsError {
  label: string;
  count: number;
}

export interface AnalyticsOutcome {
  label: string;
  count: number;
  percent: number;
  tone: string; // 'resolved', 'attempted' or anything else
}

export interface AnalyticsConcept {
  name: string;
  count: number;
  percent: number;
}

export interface AnalyticsConceptDetail {
  title: string;
  description: string;
  period_label: string;
  chart_points: { label: string; count: number }[];
  grouped_errors: AnalyticsError[];
  outcomes: AnalyticsOutcome[];
  topics: string[];
  note: string;
}

// Stats for the instructor dashboard.
export interface AnalyticsResponse {
  analysed_sessions: number;
  detected_errors: number;
  concepts: AnalyticsConcept[];
  recurring_errors: AnalyticsError[];
  details: Record<string, AnalyticsConceptDetail>;
}

// AI summary for one error type, from /api/analytics/insights.
export interface InsightsResponse {
  error_type: string;
  summary: string;
  low_data: boolean; // true when there's too little data to be reliable
  generated: boolean; // true when the summary came from the LLM
}

// The semester option is hardcoded and will need updating each semester.
export type AnalyticsDateRange =
  "today" | "last_7_days" | "last_month" | "semester_2_2026";
