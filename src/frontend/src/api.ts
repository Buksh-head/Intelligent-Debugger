// API client for the FastAPI backend (src/backend). Types live in ./types.

import axios from "axios";
import { supabase } from "./lib/supabaseClient";
import type {
  AnalyticsResponse,
  AnalyticsDateRange,
  ChatMessageRecord,
  ExecutionResponse,
  FeedbackMode,
  Finding,
  HintResponse,
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
export async function executeCode(
  code: string,
  course?: string,
  language?: string,
  sessionId?: string,
): Promise<ExecutionResponse> {
  const response = await axios.post<ExecutionResponse>(
    `${API_URL}/api/execute`,
    {
      code,
      course,
      language,
      session_id: sessionId,
    },
  );
  return response.data;
}

// Gets the next hint, or the full answer in socratic mode.
// Send the student's reply and the last hint so the backend
// can decide whether to move to the next stage.
export async function getHint(
  errorId: number,
  finding: Finding,
  execution: ExecutionResponse,
  studentMessage = "",
  previousHint = "",
  mode: FeedbackMode = "hints",
): Promise<HintResponse> {
  const response = await axios.post<HintResponse>(
    `${API_URL}/api/hints`,
    {
      error_id: errorId,
      finding,
      execution,
      student_message: studentMessage,
      previous_hint: previousHint,
      mode,
    },
    // Hints come from Groq's hosted LLM. The long timeout is left over from
    // when the model ran locally and could take minutes to load.
    { timeout: 300000 },
  );
  return response.data;
}

// Gets error stats for the instructor dashboard, by date range and course.
export async function getCohortAnalytics(
  dateRange: AnalyticsDateRange,
  course?: string,
): Promise<AnalyticsResponse> {
  const response = await axios.get<AnalyticsResponse>(
    `${API_URL}/api/analytics/cohort`,
    {
      params: { date_range: dateRange, course },
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
    { params: { date_range: dateRange, course: course || undefined }, signal },
  );
  return response.data;
}

// Student session routes need the student's login, sent as a bearer token.
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

// Saves the editor code and the latest run result.
export async function saveSessionState(
  sessionId: string,
  code: string,
  lastExecution: ExecutionResponse | null,
): Promise<void> {
  await axios.put(
    `${studentSessionUrl(sessionId)}/state`,
    { code, last_execution: lastExecution },
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
