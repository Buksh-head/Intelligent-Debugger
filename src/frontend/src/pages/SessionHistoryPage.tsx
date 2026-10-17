/**
 * The student's session history. Lists every debugging session saved to
 * their account, lets them continue one where they left off, or start a
 * new one for a course and language.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Bug, Check, ChevronDown, ChevronUp, CircleHelp, FileText, LogOut, Moon, Pencil, Sun, Trash2, User } from 'lucide-react';
import { deleteStudentData, listStudentSessions, renameStudentSession } from '../api';
import { useAuth } from '../auth/useAuth';
import { courses, findCourse, languages } from '../session/courses';
import { timeAgo } from '../session/timeAgo';
import { useStudentSession } from '../session/useStudentSession';
import type { StudentSessionSummary } from '../types';
import { type Theme, getInitialTheme, themeStorageKey } from '../theme';

const appLogo = '/error-guide-logo.png';

type SortOrder = 'newest' | 'oldest';

// A session whose last run finished cleanly, with nothing left unresolved.
const hasPassed = (session: StudentSessionSummary): boolean =>
  session.last_run_passed === true && !session.has_unresolved_error;

// The row title: the name the student gave the session, otherwise its
// latest error as the student saw it.
const sessionTitle = (session: StudentSessionSummary): string => {
  if (session.title) return session.title;
  if (hasPassed(session)) return 'Code ran successfully';
  if (!session.latest_error_type) return 'No errors yet';
  return session.latest_error_message
    ? `${session.latest_error_type}: ${session.latest_error_message}`
    : session.latest_error_type;
};

export default function SessionHistoryPage() {
  const navigate = useNavigate();
  const { session: login, signOut } = useAuth();
  const { session: activeSession, startSession, resumeSession, endSession } = useStudentSession();
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  const [sessions, setSessions] = useState<StudentSessionSummary[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [sortOrder, setSortOrder] = useState<SortOrder>('newest');
  const [course, setCourse] = useState('');
  const [language, setLanguage] = useState('');
  // The session the delete pop-up is asking about, if it is open.
  const [confirming, setConfirming] = useState<StudentSessionSummary | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // The session being renamed, if any, and the name typed so far.
  const [renaming, setRenaming] = useState<{ id: string; draft: string } | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
  // Set by Escape so the blur that follows closes the box without saving.
  const cancelRename = useRef(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(themeStorageKey, theme);
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    listStudentSessions()
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const sortedSessions = [...(sessions ?? [])].sort((a, b) => {
    const difference = new Date(b.last_activity).getTime() - new Date(a.last_activity).getTime();
    return sortOrder === 'newest' ? difference : -difference;
  });

  const handleStart = (event: FormEvent) => {
    event.preventDefault();
    if (!course) return;
    startSession({ course, language: language || findCourse(course)?.language || 'Python' });
    navigate('/student');
  };

  const handleContinue = (saved: StudentSessionSummary) => {
    resumeSession({ id: saved.id, course: saved.course ?? '', language: saved.language ?? '' });
    navigate('/student');
  };

  // Deleting a session: the bin icon opens a pop-up that asks first.
  const askToDelete = (saved: StudentSessionSummary) => {
    setDeleteError(null);
    setConfirming(saved);
  };

  const closeDeletePopup = () => {
    if (isDeleting) return;
    setConfirming(null);
  };

  const handleDelete = async () => {
    if (!confirming) return;
    const sessionId = confirming.id;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteStudentData(sessionId);
      setSessions((current) => (current ?? []).filter((saved) => saved.id !== sessionId));
      setConfirming(null);
      // A deleted session can't stay open, or later runs would be saved under it.
      if (activeSession?.id === sessionId) endSession();
    } catch {
      setDeleteError('Could not delete this session. Try again.');
    } finally {
      setIsDeleting(false);
    }
  };

  const startRename = (saved: StudentSessionSummary) => {
    setRenameError(null);
    setRenaming({ id: saved.id, draft: saved.title ?? '' });
  };

  // Shows the new name straight away and puts the old one back if the save
  // fails. A blank name goes back to the default.
  const saveRename = async () => {
    if (!renaming) return;
    const { id, draft } = renaming;
    setRenaming(null);
    const title = draft.trim() || null;
    const previous = sessions?.find((saved) => saved.id === id)?.title ?? null;
    if (title === previous) return;

    const setTitle = (value: string | null) =>
      setSessions((current) => (current ?? []).map((saved) => (saved.id === id ? { ...saved, title: value } : saved)));
    setTitle(title);
    try {
      await renameStudentSession(id, title ?? '');
    } catch {
      setTitle(previous);
      setRenameError('Could not rename this session. Try again.');
    }
  };

  const handleLogout = async () => {
    endSession();
    await signOut();
    navigate('/');
  };

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-base-100 p-3 text-base-content sm:p-5">
      <header className="navbar sticky top-0 z-10 mb-4 w-full shrink-0 flex-row items-start gap-4 bg-base-100 px-0 lg:items-center">
        <div className="flex flex-1 items-center gap-3 pl-1 sm:pl-2">
          <img src={appLogo} alt="Error Guide logo" className="h-16 w-16 shrink-0 rounded-box object-contain sm:h-[88px] sm:w-[88px]" />
          <div className="min-w-0">
            <h1 className="font-mono text-xl font-semibold leading-tight tracking-wide text-primary sm:text-2xl sm:tracking-wider lg:text-3xl">ERROR GUIDE</h1>
            <p className="mt-1">Student View | Session History</p>
          </div>
        </div>

        {/* Short explanation of the page. */}
        <div className="dropdown dropdown-end -translate-x-1 sm:-translate-x-2">
          <button type="button" tabIndex={0} className="btn btn-circle btn-ghost h-15 w-15 self-start lg:self-auto" aria-label="Help">
            <CircleHelp size={26} />
          </button>
          <div tabIndex={0} className="dropdown-content z-20 mt-3 w-72 rounded-xl border border-base-300 bg-base-100 p-4 text-sm shadow-xl">
            Every debugging session is saved to your account. Choose <strong>Continue</strong> to pick
            up where you left off, with your code and the assistant's hints, or start a new session
            for another course. The bin deletes a session and everything saved with it.
          </div>
        </div>

        {/* Profile menu: account and log out. */}
        <div className="dropdown dropdown-end self-start -translate-x-1 sm:-translate-x-2 lg:self-auto">
          <button type="button" tabIndex={0} className="btn btn-circle btn-primary h-15 w-15" aria-label="Open profile menu">
            <User size={30} />
          </button>
          <div tabIndex={0} className="dropdown-content z-20 mt-3 w-64 rounded-xl border border-base-300 bg-base-100 p-4 shadow-xl">
            <div className="mb-4 flex items-center gap-3 border-b border-base-300 pb-3">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary text-primary-content">
                <User size={24} />
              </div>
              <div className="min-w-0">
                <div className="font-semibold">Student</div>
                <div className="truncate text-sm text-base-content/60">{login?.user.email ?? 'Student account'}</div>
              </div>
            </div>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="font-medium">Theme</div>
                <div className="text-sm text-base-content/60">
                  {theme === 'dark' ? 'Dark mode' : 'Light mode'}
                </div>
              </div>
              <button
                type="button"
                className="btn btn-sm btn-circle btn-outline"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              >
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              </button>
            </div>
            <button type="button" className="btn btn-error w-full" onClick={handleLogout}>
              <LogOut size={16} />
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="flex min-h-0 w-full min-w-0 flex-1 flex-col px-1 sm:px-2">
        <div className="shrink-0">
          <h2 className="text-2xl font-bold">Your debugging sessions</h2>
          <p className="mt-1 text-sm text-base-content/70">View and continue your past debugging sessions, or start a new one.</p>

          {/* Start a new session. */}
          <form
            onSubmit={handleStart}
            className="mt-4 grid gap-4 rounded-box border border-base-300 bg-base-200 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          >
          <label className="flex flex-col gap-1">
            <span className="text-sm">Course</span>
            <select
              className="select select-bordered w-full bg-base-100"
              value={course}
              onChange={(event) => {
                setCourse(event.target.value);
                setLanguage(findCourse(event.target.value)?.language ?? '');
              }}
              required
            >
              <option value="" disabled>Select a course</option>
              {courses.map((option) => (
                <option key={option.code} value={option.code} disabled={!option.available}>
                  {option.code} {option.name}{option.available ? '' : ' (Coming soon)'}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-sm">Programming language</span>
            <select
              className="select select-bordered w-full bg-base-100"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
            >
              <option value="" disabled>Select a language</option>
              {languages.map((option) => (
                <option key={option.name} value={option.name} disabled={!option.available}>
                  {option.name}{option.available ? '' : ' (Coming soon)'}
                </option>
              ))}
            </select>
          </label>

          <button type="submit" className="btn btn-primary sm:min-w-44" disabled={!course}>
            Start session
          </button>
          </form>
        </div>

        {/* Saved sessions. */}
        <div className="mt-6 min-h-0 flex-1 overflow-y-auto">
          {sessions === null && !loadError && (
            <p className="flex items-center gap-2 py-8 text-sm text-base-content/70">
              <span className="loading loading-spinner loading-sm"></span>
              Loading your sessions...
            </p>
          )}

          {renameError && (
            <div role="alert" className="alert alert-error mb-3 text-sm">{renameError}</div>
          )}

          {(sessions !== null || loadError) && (
            <div className="w-full min-w-0">
              <table className="table w-full">
                <thead>
                  <tr className="text-base-content">
                    <th className="sticky top-0 z-10 bg-base-100">Session / Error</th>
                    <th className="sticky top-0 z-10 bg-base-100 hidden sm:table-cell">Course</th>
                    <th className="sticky top-0 z-10 bg-base-100 hidden sm:table-cell">Language</th>
                    <th className="sticky top-0 z-10 bg-base-100" aria-sort={sortOrder === 'newest' ? 'descending' : 'ascending'}>
                      <button
                        type="button"
                        className="inline-flex items-center gap-1"
                        onClick={() => setSortOrder(sortOrder === 'newest' ? 'oldest' : 'newest')}
                        title={sortOrder === 'newest' ? 'Showing newest first' : 'Showing oldest first'}
                      >
                        Last activity
                        {sortOrder === 'newest' ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                      </button>
                    </th>
                    <th className="sticky top-0 z-10 bg-base-100"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedSessions.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-sm text-base-content/70">
                        No data available.
                      </td>
                    </tr>
                  ) : sortedSessions.map((saved) => (
                    // Clicking anywhere on the row continues the session. The Continue
                    // button stays for keyboard and screen reader users.
                    <tr
                      key={saved.id}
                      className="cursor-pointer hover:bg-base-200"
                      onClick={() => handleContinue(saved)}
                    >
                      <td>
                        <div className="flex items-center gap-3">
                          {saved.has_unresolved_error ? (
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-error text-error-content" title="Has an unresolved error">
                              <Bug size={14} />
                            </span>
                          ) : hasPassed(saved) ? (
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-success text-success-content" title="Code ran successfully">
                              <Check size={14} />
                            </span>
                          ) : (
                            <FileText size={22} className="shrink-0 text-base-content/70" />
                          )}
                          <div className="min-w-0">
                            {renaming?.id === saved.id ? (
                              <input
                                type="text"
                                className="input input-bordered input-sm w-full font-semibold"
                                aria-label="Session name"
                                placeholder={sessionTitle({ ...saved, title: null })}
                                maxLength={100}
                                autoFocus
                                value={renaming.draft}
                                // Typing in the box must not also open the session.
                                onClick={(event) => event.stopPropagation()}
                                onChange={(event) => setRenaming({ id: saved.id, draft: event.target.value })}
                                // Both keys finish through onBlur, so the name is saved once.
                                onKeyDown={(event) => {
                                  if (event.key === 'Escape') cancelRename.current = true;
                                  if (event.key === 'Enter' || event.key === 'Escape') event.currentTarget.blur();
                                }}
                                onBlur={() => {
                                  if (cancelRename.current) {
                                    cancelRename.current = false;
                                    setRenaming(null);
                                  } else {
                                    void saveRename();
                                  }
                                }}
                              />
                            ) : (
                              <div className={`font-semibold ${!saved.title && hasPassed(saved) ? 'text-success' : ''}`}>{sessionTitle(saved)}</div>
                            )}
                            <div className="text-xs text-base-content/60 sm:hidden">
                              {[saved.course, saved.language].filter(Boolean).join(' | ')}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="hidden sm:table-cell" title={findCourse(saved.course)?.name}>{saved.course ?? '-'}</td>
                      <td className="hidden sm:table-cell">{saved.language ?? '-'}</td>
                      <td className="whitespace-nowrap">{timeAgo(saved.last_activity)}</td>
                      <td className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleContinue(saved);
                            }}
                          >
                            Continue
                            <ArrowRight size={14} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm btn-square"
                            onClick={(event) => {
                              // Renaming must not also open the session.
                              event.stopPropagation();
                              startRename(saved);
                            }}
                            aria-label={`Rename session: ${sessionTitle(saved)}`}
                            title="Rename this session"
                          >
                            <Pencil size={16} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-error btn-sm btn-square"
                            onClick={(event) => {
                              // Deleting must not also open the session.
                              event.stopPropagation();
                              askToDelete(saved);
                            }}
                            aria-label={`Delete session: ${sessionTitle(saved)}`}
                            title="Delete this session"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {/* Asks before deleting, since a deleted session can't be brought back. */}
      {confirming && (
        <div
          className="modal modal-open"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-session-title"
          onKeyDown={(event) => {
            if (event.key === 'Escape') closeDeletePopup();
          }}
        >
          <div className="modal-box">
            <h3 id="delete-session-title" className="text-lg font-bold">Delete this session?</h3>
            <p className="mt-3 text-sm">
              Are you sure you want to delete <strong>{sessionTitle(confirming)}</strong>
              {confirming.course ? ` (${confirming.course})` : ''}? Its code, errors, hints and chat will be
              deleted. This can't be undone.
            </p>
            {deleteError && <p className="mt-3 text-sm text-error">{deleteError}</p>}
            <div className="modal-action">
              <button type="button" className="btn" onClick={closeDeletePopup} disabled={isDeleting} autoFocus>
                Cancel
              </button>
              <button type="button" className="btn btn-error" onClick={handleDelete} disabled={isDeleting}>
                {isDeleting ? <span className="loading loading-spinner loading-sm"></span> : 'Delete'}
              </button>
            </div>
          </div>
          {/* Clicking outside the pop-up closes it. */}
          <button type="button" className="modal-backdrop" onClick={closeDeletePopup} aria-label="Close" />
        </div>
      )}
    </div>
  );
}
