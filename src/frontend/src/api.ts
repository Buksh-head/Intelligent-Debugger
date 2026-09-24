import axios from 'axios';
import { supabase } from './lib/supabaseClient';
import type { AnalyticsResponse, AnalyticsDateRange, ExecutionResponse, Finding, HintResponse } from './types';

const API_URL = import.meta.env.VITE_API_URL ?? '';

async function authHeaders() {
  const { data } = await supabase.auth.getSession();

  const token = data.session?.access_token;

  return token
    ? {
        Authorization: `Bearer ${token}`,
      }
    : {};
}


export async function executeCode(
  code: string,
  expectedBehaviour: string,
  course?: string,
  language?: string,
): Promise<ExecutionResponse> {
  const response = await axios.post<ExecutionResponse>(
    `${API_URL}/api/execute`,
    {
      code,
      expected_behaviour: expectedBehaviour,
      course,
      language,
    },
    {
      headers: await authHeaders(),
    },
  );

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
      finding,
      execution,
      student_message: studentMessage,
      previous_hint: previousHint,
    },
    {
      timeout: 300000,
      headers: await authHeaders(),
    },
  );

  return response.data;
}


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
