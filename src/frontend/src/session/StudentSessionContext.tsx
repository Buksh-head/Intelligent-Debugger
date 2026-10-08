/**
 * Stores the anonymous student session (ID, course and language) and
 * shares it with the rest of the app.
 */
import { useState, type ReactNode } from 'react';
import { StudentSessionContext, type StudentContext, type StudentSession } from './context';

// sessionStorage keys. Changing these logs out anyone mid-session.
const contextStorageKey = 'debugging-assistant.student-context';
const sessionIdStorageKey = 'debugging-assistant.session-id';

// Restores the session after a page refresh. sessionStorage is per tab, so a
// new tab or a closed browser starts without one.
const readStoredSession = (): StudentSession | null => {
  try {
    const storedContext = sessionStorage.getItem(contextStorageKey);
    if (!storedContext) return null;

    const { course = '', language = '' } = JSON.parse(storedContext) as Partial<StudentContext>;
    // Tabs opened before session IDs existed have a context but no ID.
    let id = sessionStorage.getItem(sessionIdStorageKey);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(sessionIdStorageKey, id);
    }
    return { id, course, language };
  } catch {
    return null;
  }
};

export function StudentSessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<StudentSession | null>(readStoredSession);

  // Always issues a fresh ID, so nothing from an earlier session carries over.
  const startSession = (context: StudentContext) => {
    const next = { ...context, id: crypto.randomUUID() };
    sessionStorage.setItem(contextStorageKey, JSON.stringify(context));
    sessionStorage.setItem(sessionIdStorageKey, next.id);
    setSession(next);
  };

  // Clears the session from this tab only.
  const endSession = () => {
    sessionStorage.removeItem(contextStorageKey);
    sessionStorage.removeItem(sessionIdStorageKey);
    setSession(null);
  };

  return (
    <StudentSessionContext.Provider value={{ session, startSession, endSession }}>
      {children}
    </StudentSessionContext.Provider>
  );
}
