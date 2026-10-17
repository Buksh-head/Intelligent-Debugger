// Types mirroring the backend's API schemas (src/backend/app/models.py).
// Keep these in sync if that file changes.

// Execution and hint types describe the feedback exchanged while a student
// runs code and works through the debugging assistant.
export interface ExecutionError {
  error_type: string;
  message: string;
  line_number: number | null;
  code_snippet: string | null;
}

export interface ExecutionResponse {
  stdout: string;
  stderr: string;
  exit_code: number | null;
  status: string | null;
  timed_out: boolean;
  error: ExecutionError | null;
  error_id: number | null;
}

// Info sent back to the hints endpoint to say which error to help with.
export interface Finding {
  error_type: string;
  line_number: number | null;
  failing_code_snippet: string;
}

// One step of the staged hint chat.
export interface HintStage {
  stage: number;
  text: string | null;
  intent: string | null;          // how the classifier read the student's reply
  advanced_softly: boolean;       // moved on after vague replies rather than a real answer
  resource_url: string | null;    // curated link, present while a resource is active
  resource_label: string | null;  // its title, e.g. "Dictionaries in Python"
  gate_on_url: boolean;           // true while the student still owes the check answer
}

export type FeedbackMode = 'hints' | 'socratic';

export interface SocraticAnswer {
  diagnosis: string | null;  // what the code does and why it fails
  fix: string | null;        // the change that resolves it, may contain code
}

export interface Attribution {
  feature: string;
  label: string;   // the only part a student sees
  weight: number;
}

// Every field may be missing; the whole object is null when the explanation layer fails.
export interface Explanation {
  reasoning: string | null;
  misconception: string | null;
  confidence: number | null;
  attributions: Attribution[] | null;
  counterfactual_question: string | null;
}

export interface HintResponse {
  status: string;
  execution: ExecutionResponse;
  finding: Finding;
  hints: HintStage[];              // empty in socratic mode
  answer: SocraticAnswer | null;   // only set in socratic mode
  explanation?: Explanation | null; // only set in socratic mode
}

// One message in the Student View chat.
export type ChatMessage = {
  role: 'student' | 'assistant' | 'event'; // 'event' marks a resubmission within the chat
  text: string;
  stage?: number;
  resourceUrl?: string | null;   // link from the curated list, if this message offers one
  resourceLabel?: string | null; // the link's title
  gated?: boolean;               // true while the student still owes the check answer
  answer?: SocraticAnswer;       // set on a socratic-mode reply, rendered as diagnosis and fix
  explanation?: Explanation | null; // how the system reached that answer
};

// A chat message as saved to the student's account. body holds every
// ChatMessage field except role.
export interface ChatMessageRecord {
  position: number;
  role: ChatMessage['role'];
  body: Omit<ChatMessage, 'role'>;
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
  last_execution: ExecutionResponse | null;
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

// The semester option is hardcoded and will need updating each semester.
export type AnalyticsDateRange = 'today' | 'last_7_days' | 'last_month' | 'semester_2_2026';
