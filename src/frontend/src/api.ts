// API client for the FastAPI backend (src/backend). Types live in ./types.

import axios from "axios";
import { supabase } from "./lib/supabaseClient";
import type {
  AnalyticsResponse,
  AnalyticsDateRange,
  ChatMessageRecord,
  Stage1Hint,
  SocraticAnswer,
  FollowUpHint,
  OutputCheck,
  HintTurn,
  ExecutionResponse,
  SavedErrorRef,
  SavedExecution,
  InsightsResponse,
  StudentSessionDetail,
  StudentSessionSummary,
} from "./types";

// Backend address. Empty by default, so calls go to /api on the same site
// and the Vite proxy forwards them to the backend.
const API_URL = import.meta.env.VITE_API_URL ?? "";

// These small typed wrappers keep request details in one place and make
// backend responses available to the React components with checked types.
// Runs the student's code in the sandbox and returns the output or error.
// stdin is fed to the program's input() calls.
export async function executeCode(
  code: string,
  course?: string,
  language?: string,
  sessionId?: string,
  stdin = "",
  expected = "",
): Promise<ExecutionResponse> {
  const response = await axios.post<ExecutionResponse>(
    `${API_URL}/api/execute`,
    {
      code,
      stdin,
      course,
      language,
      session_id: sessionId,
      expected: expected.trim() ? expected : undefined,
    },
  );
  return response.data;
}

// Gets the stage 1 hint for a run: one leading question that points at the
// cause of the error without giving the fix. Sends back the code, input and
// result of that run, so the backend does not have to run the code again.
// expected: the output the student expected, for a run that finished but
// printed something else (a logic error). saved: the session and saved error,
// so the hint is recorded for the instructor dashboard.
export async function getStage1Hint(
  code: string,
  stdin: string,
  execution: ExecutionResponse,
  expected?: string,
  saved: SavedErrorRef = {},
): Promise<Stage1Hint> {
  const response = await axios.post<Stage1Hint>(
    `${API_URL}/api/hints/stage1`,
    {
      code,
      stdin,
      execution: {
        stdout: execution.stdout,
        stderr: execution.stderr,
        exit_code: execution.exit_code,
        timed_out: execution.timed_out,
      },
      expected,
      ...saved,
    },
    // The model call can take several seconds.
    { timeout: 120000 },
  );
  return response.data;
}

// Socratic mode: the whole answer for a run, what went wrong and how to fix
// it, with how it was worked out. Takes the same run details as the stage 1
// hint. Unlike the hints, the answer is meant to give the fix away.
export async function getSocraticAnswer(
  code: string,
  stdin: string,
  execution: ExecutionResponse,
  expected?: string,
  saved: SavedErrorRef = {},
): Promise<SocraticAnswer> {
  const response = await axios.post<SocraticAnswer>(
    `${API_URL}/api/answer`,
    {
      code,
      stdin,
      execution: {
        stdout: execution.stdout,
        stderr: execution.stderr,
        exit_code: execution.exit_code,
        timed_out: execution.timed_out,
      },
      expected,
      ...saved,
    },
    { timeout: 120000 },
  );
  return response.data;
}

// Stage 2: sends every question asked so far with the student's replies (the
// stage 1 question first) and gets back either a new leading question or a
// short answer, depending on how close the latest reply is.
export async function getFollowUpHint(
  code: string,
  stdin: string,
  execution: ExecutionResponse,
  turns: HintTurn[],
  expected?: string,
  saved: SavedErrorRef = {},
): Promise<FollowUpHint> {
  const response = await axios.post<FollowUpHint>(
    `${API_URL}/api/hints/followup`,
    {
      code,
      stdin,
      execution: {
        stdout: execution.stdout,
        stderr: execution.stderr,
        exit_code: execution.exit_code,
        timed_out: execution.timed_out,
      },
      turns,
      expected,
      ...saved,
    },
    { timeout: 120000 },
  );
  return response.data;
}

// Compares what a finished run printed with what the student expected it to
// print. No model call and no new run, so it is quick. For a saved run
// (sessionId and submissionId), a difference is saved as a logic error.
export async function checkOutput(
  code: string,
  stdout: string,
  expected: string,
  sessionId?: string,
  submissionId?: number | null,
): Promise<OutputCheck> {
  const response = await axios.post<OutputCheck>(
    `${API_URL}/api/check-output`,
    {
      code,
      stdout,
      expected,
      session_id: sessionId,
      submission_id: submissionId ?? undefined,
    },
  );
  return response.data;
}

// Gets error stats for the instructor dashboard, by date range and course.
// Needs an instructor login.
export async function getCohortAnalytics(
  dateRange: AnalyticsDateRange,
  course?: string,
): Promise<AnalyticsResponse> {
  const response = await axios.get<AnalyticsResponse>(
    `${API_URL}/api/analytics/cohort`,
    {
      params: { date_range: dateRange, course },
      headers: await authHeaders(),
    },
  );
  return response.data;
}

// Gets the AI summary for one error type. The signal cancels the request
// when the instructor switches to another error type.
export async function getInsights(
  errorType: string,
  dateRange: AnalyticsDateRange,
  course?: string,
  signal?: AbortSignal,
): Promise<InsightsResponse> {
  const response = await axios.get<InsightsResponse>(
    `${API_URL}/api/analytics/insights/${encodeURIComponent(errorType)}`,
    {
      params: { date_range: dateRange, course: course || undefined },
      headers: await authHeaders(),
      signal,
    },
  );
  return response.data;
}

// Session and dashboard routes need the user's login, sent as a bearer token.
async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const studentSessionUrl = (sessionId: string) =>
  `${API_URL}/api/student/sessions/${encodeURIComponent(sessionId)}`;

// Records a new session against the logged-in student. Safe to repeat.
export async function createStudentSession(
  sessionId: string,
  course: string,
  language: string,
): Promise<void> {
  await axios.post(
    `${API_URL}/api/student/sessions`,
    { id: sessionId, course: course || null, language: language || null },
    { headers: await authHeaders() },
  );
}

// The logged-in student's sessions, most recently used first.
export async function listStudentSessions(): Promise<StudentSessionSummary[]> {
  const response = await axios.get<StudentSessionSummary[]>(
    `${API_URL}/api/student/sessions`,
    {
      headers: await authHeaders(),
    },
  );
  return response.data;
}

// Loads a saved session, or null if the student has none with this ID.
export async function getStudentSession(
  sessionId: string,
): Promise<StudentSessionDetail | null> {
  try {
    const response = await axios.get<StudentSessionDetail>(
      studentSessionUrl(sessionId),
      {
        headers: await authHeaders(),
      },
    );
    return response.data;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 404) return null;
    throw err;
  }
}

// Saves chat messages. Positions already saved are skipped by the backend.
export async function appendChatMessages(
  sessionId: string,
  messages: ChatMessageRecord[],
): Promise<void> {
  await axios.post(
    `${studentSessionUrl(sessionId)}/messages`,
    { messages },
    { headers: await authHeaders() },
  );
}

// Saves the editor code, the latest run (with its input) and the output the
// student expects.
export async function saveSessionState(
  sessionId: string,
  code: string,
  lastExecution: SavedExecution | null,
  expected = "",
): Promise<void> {
  await axios.put(
    `${studentSessionUrl(sessionId)}/state`,
    {
      code,
      last_execution: lastExecution,
      expected_output: expected.trim() ? expected : null,
    },
    { headers: await authHeaders() },
  );
}

// Renames one of the logged-in student's sessions. A blank title goes back
// to the default name. Fails with a 404 if the session isn't the student's.
export async function renameStudentSession(
  sessionId: string,
  title: string,
): Promise<void> {
  await axios.patch(
    studentSessionUrl(sessionId),
    { title },
    { headers: await authHeaders() },
  );
}

// Deletes everything stored for one of the logged-in student's sessions,
// including its chat. The backend keeps only anonymous daily counts for the
// instructor dashboard. Fails with a 404 if the session isn't the student's.
export async function deleteStudentData(sessionId: string): Promise<void> {
  await axios.delete(studentSessionUrl(sessionId), {
    headers: await authHeaders(),
  });
}
