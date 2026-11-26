/**
 * Rebuilds the Student View from the copy saved on the student's account, so
 * a session can be continued after a refresh or from the session history:
 * the code, the last run, the expected output, and the hint conversation
 * about that run (the stage 1 question and every reply and follow-up).
 */
import { createStudentSession, getStudentSession } from "../api";
import type {
  ChatMessageRecord,
  ExecutionResponse,
  FollowUpHint,
  OutputCheck,
  SavedHintBody,
  SocraticAnswer,
  Stage1Hint,
  StudentSessionDetail,
} from "../types";

// One answered follow-up: what the student replied and the response to it.
export type HintStep = { reply: string; response: FollowUpHint };

// The Student View state rebuilt from a saved session.
export type RestoredSession = {
  code: string;
  result: ExecutionResponse | null;
  stdin: string;
  expected: string;
  // The hint conversation about the last run, if there was one.
  hint: Stage1Hint | null;
  // The Socratic answer for the last run, if the student asked for it.
  answer: SocraticAnswer | null;
  steps: HintStep[];
  // For a hint about wrong output: the check it was about.
  check: OutputCheck | null;
  checkedExpected: string;
};

const isSavedHint = (
  body: ChatMessageRecord["body"],
): body is SavedHintBody =>
  typeof (body as { kind?: unknown }).kind === "string";

export function restoreSession(detail: StudentSessionDetail): RestoredSession {
  const saved = detail.last_execution;
  let result: ExecutionResponse | null = null;
  let stdin = "";
  if (saved) {
    const { stdin: savedStdin, ...rest } = saved;
    result = rest;
    stdin = savedStdin ?? "";
  }
  const restored: RestoredSession = {
    code: detail.code ?? "",
    result,
    stdin,
    expected: detail.expected_output ?? "",
    hint: null,
    answer: null,
    steps: [],
    check: null,
    checkedExpected: "",
  };

  // The conversation is everything after the last "run" event.
  const bodies = [...detail.messages]
    .sort((a, b) => a.position - b.position)
    .map((m) => m.body)
    .filter(isSavedHint);
  const lastRun = bodies.map((b) => b.kind).lastIndexOf("run");
  const conversation = bodies.slice(lastRun + 1);
  const first = conversation[0];
  if (!result || (first?.kind !== "hint" && first?.kind !== "answer"))
    return restored;

  // The answer can come first (asked for straight away) or after the hints.
  if (first.kind === "hint") restored.hint = first.hint;
  restored.check = first.check ?? null;
  restored.checkedExpected = first.expected ?? "";
  let reply: string | null = null;
  for (const body of conversation) {
    if (body.kind === "answer") restored.answer = body.answer;
    else if (body.kind === "reply") reply = body.text;
    else if (body.kind === "followup" && reply !== null) {
      restored.steps.push({ reply, response: body.followup });
      reply = null;
    }
  }
  return restored;
}

// The saved copy of this session, or null for a new one. A session the
// backend doesn't know yet is registered, so its work can be saved from now on.
export async function loadOrRegisterSession(
  sessionId: string,
  course: string,
  language: string,
): Promise<StudentSessionDetail | null> {
  const detail = await getStudentSession(sessionId);
  if (detail) return detail;
  await createStudentSession(sessionId, course, language);
  return null;
}
