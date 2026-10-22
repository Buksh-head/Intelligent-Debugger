/**
 * Converts the Student View's chat to and from the copy saved on the
 * student's account, so a session can be continued after a refresh or
 * from the session history.
 */
import { createStudentSession, getStudentSession } from "../api";
import type {
  ChatMessage,
  ChatMessageRecord,
  ExecutionResponse,
  StudentSessionDetail,
} from "../types";

// The Student View state rebuilt from a saved session.
export type RestoredSession = {
  code: string;
  result: ExecutionResponse | null;
  messages: ChatMessage[];
  currentStage: number | null;
};

// Messages from index `start` onwards, numbered by their place in the chat.
export const toRecords = (
  messages: ChatMessage[],
  start: number,
): ChatMessageRecord[] =>
  messages
    .slice(start)
    .map(({ role, ...body }, i) => ({ position: start + i, role, body }));

export const fromRecords = (records: ChatMessageRecord[]): ChatMessage[] =>
  [...records]
    .sort((a, b) => a.position - b.position)
    .map(({ role, body }) => ({ ...body, role }));

export function restoreSession(detail: StudentSessionDetail): RestoredSession {
  const messages = fromRecords(detail.messages);
  const result = detail.last_execution;

  // Feedback for the latest run starts after the last "Code resubmitted" divider.
  const runStart = messages.reduce(
    (start, message, index) => (message.role === "event" ? index + 1 : start),
    0,
  );
  const lastHintThisRun = [...messages.slice(runStart)]
    .reverse()
    .find(
      (message) =>
        message.role === "assistant" &&
        !message.answer &&
        message.stage != null,
    );

  return {
    code: detail.code ?? "",
    result,
    messages,
    // Hints carry on from the stage reached, as long as the error is still showing.
    currentStage:
      result?.error && lastHintThisRun ? lastHintThisRun.stage! : null,
  };
}

// The saved copy of this session, or null for a new one. A session the
// backend doesn't know yet is registered, so its chat can be saved from now on.
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
