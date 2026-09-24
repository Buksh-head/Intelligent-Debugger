// Types mirroring the backend's API schemas (src/backend/app/models.py).
// Keep these in sync if that file changes.

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

export interface Finding {
  error_type: string;
  line_number: number | null;
  failing_code_snippet: string;
}

export interface HintStage {
  stage: number;
  text: string | null;
  intent: string | null;          // how the classifier read the student's reply
  advanced_softly: boolean;       // moved on after vague replies rather than a real answer
  resource_url: string | null;    // curated link, present while a resource is active
  resource_label: string | null;  // its title, e.g. "Dictionaries in Python"
  gate_on_url: boolean;           // true while the student still owes the check answer
}

export interface HintResponse {
  status: string;
  execution: ExecutionResponse;
  finding: Finding;
  hints: HintStage[];
}

export interface AnalyticsError {
  label: string;
  count: number;
}

export interface AnalyticsOutcome {
  label: string;
  count: number;
  percent: number;
  tone: string;
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

export interface AnalyticsResponse {
  analysed_sessions: number;
  detected_errors: number;
  concepts: AnalyticsConcept[];
  recurring_errors: AnalyticsError[];
  details: Record<string, AnalyticsConceptDetail>;
}

export type AnalyticsDateRange = 'today' | 'last_7_days' | 'last_month' | 'semester_2_2026';
