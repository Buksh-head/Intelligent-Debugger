// API client for the FastAPI backend (src/backend). Types live in ./types.

import axios from 'axios';
import type { AnalyticsResponse, AnalyticsDateRange, ExecutionResponse, FeedbackMode, Finding, HintResponse } from './types';

// Backend address. Empty by default, so calls go to /api on the same site
// and the Vite proxy forwards them to the backend.
const API_URL = import.meta.env.VITE_API_URL ?? '';

// Runs the student's code in the sandbox and returns the output or error.
export async function executeCode(
  code: string,
  expectedBehaviour: string,
  course?: string,
  language?: string,
  sessionId?: string,
): Promise<ExecutionResponse> {
  const response = await axios.post<ExecutionResponse>(`${API_URL}/api/execute`, {
    code,
    expected_behaviour: expectedBehaviour,
    course,
    language,
    session_id: sessionId,
  });
  return response.data;
}

// Gets the next hint, or the full answer in socratic mode.                   
// Send the student's reply and the last hint so the backend                  
// can decide whether to move to the next stage.   
export async function getHint(
  errorId: number,
  finding: Finding,
  execution: ExecutionResponse,
  studentMessage = '',
  previousHint = '',
  mode: FeedbackMode = 'hints',
): Promise<HintResponse> {
  const response = await axios.post<HintResponse>(
    `${API_URL}/api/hints`,
    {
      error_id: errorId,
      finding, execution,
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
export async function getCohortAnalytics(dateRange: AnalyticsDateRange, course?: string): Promise<AnalyticsResponse> {
  const response = await axios.get<AnalyticsResponse>(`${API_URL}/api/analytics/cohort`, {
    params: { date_range: dateRange, course },
  });
  return response.data;
}

// Deletes everything stored for a session. The backend keeps only
// anonymous daily counts for the instructor dashboard. Returns nothing:
// the backend replies 204 whether or not the session had data.
export async function deleteStudentData(sessionId: string): Promise<void> {
  await axios.delete(`${API_URL}/api/student-data/${encodeURIComponent(sessionId.trim())}`);
}
