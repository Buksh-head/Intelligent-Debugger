// API client for the FastAPI backend (src/backend). Types live in ./types.

import axios from 'axios';
import type { AnalyticsResponse, AnalyticsDateRange, ExecutionResponse, Finding, HintResponse } from './types';

const API_URL = import.meta.env.VITE_API_URL ?? '';

export async function executeCode(
  code: string,
  expectedBehaviour: string,
  course?: string,
  language?: string,
): Promise<ExecutionResponse> {
  const response = await axios.post<ExecutionResponse>(`${API_URL}/api/execute`, {
    code,
    expected_behaviour: expectedBehaviour,
    course,
    language,
  });
  return response.data;
}

export async function getHint(
  errorId: number,
  finding: Finding,
  execution: ExecutionResponse,
  studentMessage = '',
  previousHint = '',
): Promise<HintResponse> {
  const response = await axios.post<HintResponse>(
    `${API_URL}/api/hints`,
    {
      error_id: errorId,
      finding, execution,
      student_message: studentMessage,
      previous_hint: previousHint,
    },
    // The backend runs a local LLM (transformers, CPU inference) - this can
    // legitimately take minutes, especially the first call on a given
    // machine while the model loads. See hint_generator.py.
    { timeout: 300000 },
  );
  return response.data;
}

export async function getCohortAnalytics(dateRange: AnalyticsDateRange, course?: string): Promise<AnalyticsResponse> {
  const response = await axios.get<AnalyticsResponse>(`${API_URL}/api/analytics/cohort`, {
    params: { date_range: dateRange, course },
  });
  return response.data;
}
