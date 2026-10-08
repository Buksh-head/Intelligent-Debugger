/**
 * Types and context for the anonymous student session.
 */
import { createContext } from 'react';

// What the student picks on the setup page.
export type StudentContext = {
  course: string;
  language: string;
};

// One student debugging session. It starts when the student continues from
// the welcome page and ends on logout. The ID tags every submission, so
// persisted records stay tied to the session they came from.
export type StudentSession = StudentContext & {
  id: string;
};

export type StudentSessionContextValue = {
  session: StudentSession | null;
  startSession: (context: StudentContext) => void;
  endSession: () => void;
};

export const StudentSessionContext = createContext<StudentSessionContextValue | null>(null);
