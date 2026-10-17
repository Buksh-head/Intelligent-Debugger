/**
 * Main app component. Sets up the page routes and contains the whole
 * student page: code editor, run results and the hint chat.
 */
import { useEffect, useRef, useState } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import pythonLogo from './assets/python.jpg';
import javaLogo from './assets/java.jpg';
import javascriptLogo from './assets/js.jpg';
import { Navigate, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import InstructorDashboard from './InstructorDashboard'
import WelcomePage from './pages/WelcomePage';
import SessionHistoryPage from './pages/SessionHistoryPage';
import ProtectedRoute from './auth/ProtectedRoute';
import { useAuth } from './auth/useAuth';
import { useStudentSession } from './session/useStudentSession';
import { loadOrRegisterSession, restoreSession, toRecords } from './session/savedSession';
import type { ChatMessage, ExecutionResponse, FeedbackMode, Finding, HintStage } from './types';
import WhyThisHint from './components/WhyThisHint';
import { getTourSample, startStudentTour, tourRunStep } from './tour/studentTour';
import { hasSeenTour } from './tour/tourStatus';
import type { Driver } from 'driver.js';
import { appendChatMessages, executeCode, getHint, saveSessionState } from './api';
import { type Theme, getInitialTheme, themeStorageKey } from './theme';

import {
  ArrowLeft,
  LogOut,
  Upload,
  Play,
  SquareTerminal,
  Sparkles,
  Send,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  HandHelping,
  SquareCode,
  Sun,
  Moon,
  User,
  Bot,
  UserRound,
  BookOpen,
  ExternalLink,
  Lightbulb,
  Lock,
  CircleHelp,
  History,
} from 'lucide-react';

type MonacoEditor = Parameters<OnMount>[0];
type DecorationsCollection = ReturnType<MonacoEditor['createDecorationsCollection']>;

// Editor settings for each course. Used if the student didn't pick a language.
const courseEditorLanguages: Record<string, { monaco: string; label: string; extension: string; logo: string }> = {
  CSSE1001: { monaco: 'python', label: 'Python', extension: 'py', logo: pythonLogo },
  CSSE2002: { monaco: 'java', label: 'Java', extension: 'java', logo: javaLogo },
  ENGG1001: { monaco: 'python', label: 'Python', extension: 'py', logo: pythonLogo },
  DECO1800: { monaco: 'javascript', label: 'JavaScript', extension: 'js', logo: javascriptLogo },
};

// Editor settings for each language the student can pick at setup.
const languageEditorLanguages: Record<string, { monaco: string; label: string; extension: string; logo: string }> = {
  Python: { monaco: 'python', label: 'Python', extension: 'py', logo: pythonLogo },
  Java: { monaco: 'java', label: 'Java', extension: 'java', logo: javaLogo },
  JavaScript: { monaco: 'javascript', label: 'JavaScript', extension: 'js', logo: javascriptLogo },
};

const appLogo = '/error-guide-logo.png';

// Width split between the code and assistant panels, as the left panel's
// share in percent. Saved per session so a new session starts at 50/50.
const splitStoragePrefix = 'debugging-assistant.panel-split.';
const defaultSplit = 50;
const minSplit = 30;
const maxSplit = 70;

const clampSplit = (value: number) => Math.min(maxSplit, Math.max(minSplit, value));

// This session's saved split, or the 50/50 default.
const getSavedSplit = (sessionId: string | null): number => {
  if (!sessionId) return defaultSplit;
  try {
    const saved = Number(sessionStorage.getItem(splitStoragePrefix + sessionId));
    return saved > 0 ? clampSplit(saved) : defaultSplit;
  } catch {
    return defaultSplit; // storage can be blocked, the default still works
  }
};

// Summarises a run for the divider that separates it from earlier feedback.
const describeRun = (execution: ExecutionResponse): string => {
  if (execution.timed_out) return 'Code resubmitted: timed out';
  if (!execution.error) return 'Code resubmitted: ran successfully';
  const line = execution.error.line_number ? ` on line ${execution.error.line_number}` : '';
  return `Code resubmitted: ${execution.error.error_type}${line}`;
};

// Index of the first message in the run that message `index` belongs to.
const runStartIndex = (messages: ChatMessage[], index: number): number => {
  for (let i = index - 1; i >= 0; i--) {
    if (messages[i].role === 'event') return i + 1;
  }
  return 0;
};

function App() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  // Code and run results 
  const [code, setCode] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ExecutionResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  // Hint chat
  const [isHintLoading, setIsHintLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [currentStage, setCurrentStage] = useState<number | null>(null);
  const [hintError, setHintError] = useState<string | null>(null);

  // Hints or Answer mode
  const [feedbackMode, setFeedbackMode] = useState<FeedbackMode>('hints');
  // Whether the student has picked a mode yet this session. Until then both
  // choices are laid out; after that the last choice is offered first.
  const [hasChosenMode, setHasChosenMode] = useState(false);
  const isSocratic = feedbackMode === 'socratic';

  const navigate = useNavigate();
  const location = useLocation();
  const { signOut, session: authSession } = useAuth();
  const { session: studentSession, endSession } = useStudentSession();
  const sessionId = studentSession?.id ?? null;

  // Panel split for this session.
  const [split, setSplit] = useState(() => getSavedSplit(sessionId));
  const [isDragging, setIsDragging] = useState(false);
  // True while the intro tour has sample code in the editor. Run then shows
  // a made-up result instead of calling the backend.
  const [isTourDemo, setIsTourDemo] = useState(false);

  const selectedCourse = studentSession?.course ?? '';

  // Editor language: the student's chosen language first, then their course's, then Python.
  const editorLanguage =
    languageEditorLanguages[studentSession?.language ?? ''] ??
    courseEditorLanguages[selectedCourse] ??
    courseEditorLanguages.CSSE1001;

  // Everything below is scoped to one session. When the session changes
  // (logout, or a new start from the welcome page) it is discarded so none of
  // it can show up in the next session. Adjusting state during render rather
  // than in an effect avoids painting the old chat for a frame.
  // The session whose saved copy has been loaded, see the save effects below.
  const [syncedSessionId, setSyncedSessionId] = useState<string | null>(null);
  const [stateSessionId, setStateSessionId] = useState(sessionId);
  if (sessionId !== stateSessionId) {
    setStateSessionId(sessionId);
    setCode('');
    setIsLoading(false);
    setResult(null);
    setApiError(null);
    setIsHintLoading(false);
    setMessages([]);
    setInput('');
    setCurrentStage(null);
    setHintError(null);
    setFeedbackMode('hints');
    setHasChosenMode(false);
    setSplit(getSavedSplit(sessionId));
    setIsTourDemo(false);
    setSyncedSessionId(null);
  }

  // Requests still in flight when the session changes must not write into the
  // next one. Handlers compare against this once their request resolves.
  const sessionIdRef = useRef(sessionId);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // Saving to the student's account. Nothing is saved until the session has
  // been loaded (or registered, if it is new), so an earlier chat is never
  // overwritten. If that fails, e.g. when not logged in, the chat still works
  // but isn't saved.
  const isSynced = sessionId !== null && syncedSessionId === sessionId;
  // How many messages of this chat are already saved.
  const savedCountRef = useRef(0);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    loadOrRegisterSession(sessionId, studentSession?.course ?? '', studentSession?.language ?? '')
      .then((detail) => {
        if (cancelled) return;
        if (detail) {
          const restored = restoreSession(detail);
          setCode(restored.code);
          setResult(restored.result);
          setMessages(restored.messages);
          setCurrentStage(restored.currentStage);
          setFeedbackMode(restored.feedbackMode);
          setHasChosenMode(restored.hasChosenMode);
        }
        savedCountRef.current = detail?.messages.length ?? 0;
        setSyncedSessionId(sessionId);
      })
      .catch(() => {
        // Left unsynced: the session carries on without being saved.
      });
    return () => {
      cancelled = true;
    };
    // Course and language are only needed to register a new session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Save each new chat message. A failed save is retried with the next
  // message; the backend skips any position it already has.
  useEffect(() => {
    if (!isSynced || isTourDemo) return;
    const start = savedCountRef.current;
    if (messages.length <= start) return;
    savedCountRef.current = messages.length;
    appendChatMessages(sessionId, toRecords(messages, start)).catch(() => {
      savedCountRef.current = Math.min(savedCountRef.current, start);
    });
  }, [messages, isSynced, isTourDemo, sessionId]);

  const editorRef = useRef<MonacoEditor | null>(null);
  const decorationsRef = useRef<DecorationsCollection | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const outputRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const mainRef = useRef<HTMLElement | null>(null);
  const tourRef = useRef<Driver | null>(null);

  // The final stage reveals the answer, so there is nothing further to unlock.
  const isFinalStage = currentStage === 5;
  const sendDisabled = currentStage === null || isLoading || isHintLoading || !input.trim() || isFinalStage || isSocratic;

  // Chat history is retained between runs, so only use the first assistant
  // message after the most recent resubmission in the current diagnosis.
  const currentRunStart = messages.reduce(
    (start, message, index) => (message.role === 'event' ? index + 1 : start),
    0,
  );
  const firstHintForCurrentRun = messages
    .slice(currentRunStart)
    .find((message) => message.role === 'assistant');
  const answeredThisRun = messages.slice(currentRunStart).some((message) => message.answer);
  // The student picks Hints or Answer when they first ask for help on an
  // error. The choice holds until the code is run again, so the hints can't
  // be skipped by asking for the answer halfway through.
  const helpChosen = firstHintForCurrentRun !== undefined;
  const hintsInProgress = helpChosen && !answeredThisRun && !isFinalStage;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(themeStorageKey, theme);
  }, [theme]);

  // Keep the panel split for the rest of this session.
  useEffect(() => {
    if (!sessionId) return;
    try {
      sessionStorage.setItem(splitStoragePrefix + sessionId, String(split));
    } catch {
      // Storage can be blocked, the split just won't be kept.
    }
  }, [split, sessionId]);

  // Reload the saved theme when the student page opens.
  useEffect(() => {
    if (location.pathname === '/student') {
      setTheme(getInitialTheme());
    }
  }, [location.pathname]);

  // Highlight the failing line in the editor whenever a new result with an
  // error comes back; clear it on a clean run or a fresh loading state.
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;

    decorationsRef.current?.clear();

    const lineNumber = result?.error?.line_number;
    if (lineNumber) {
      decorationsRef.current = editor.createDecorationsCollection([
        {
          range: {
            startLineNumber: lineNumber,
            startColumn: 1,
            endLineNumber: lineNumber,
            endColumn: 1,
          },
          options: {
            isWholeLine: true,
            className: 'error-line-highlight',
          },
        },
      ]);
    }
  }, [result]);

  // Keep the newest message in view as the conversation grows.
  useEffect(() => {
    const messagesContainer = messagesContainerRef.current;
    if (!messagesContainer) return;

    messagesContainer.scrollTo({
      top: messagesContainer.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, isHintLoading]);

  // Keep the end of the output in view, where the error is shown.
  useEffect(() => {
    const output = outputRef.current;
    if (!output) return;

    output.scrollTo({ top: output.scrollHeight });
  }, [result]);

  // In the tour demo, move on from the "click Run" step once the sample
  // result is showing. This runs after render, so the error box exists.
  useEffect(() => {
    const tour = tourRef.current;
    if (!isTourDemo || !result || !tour?.isActive()) return;
    if (tour.getActiveStep()?.element === tourRunStep) tour.moveNext();
  }, [result, isTourDemo]);

  const handleEditorMount: OnMount = (editor) => {
    editorRef.current = editor;
  };

  // Dragging the panel divider. Capturing the pointer keeps the drag going
  // when it moves over the editor or off the divider.
  const handleDividerPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsDragging(true);
  };

  const handleDividerPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    const main = mainRef.current;
    if (!main) return;
    const rect = main.getBoundingClientRect();
    setSplit(clampSplit(((event.clientX - rect.left) / rect.width) * 100));
  };

  const handleDividerPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setIsDragging(false);
  };

  // Scroll to the error line and put the cursor there.
  const focusErrorLine = (lineNumber: number) => {
    const editor = editorRef.current;
    if (!editor) return;

    editor.revealLineInCenter(lineNumber);
    editor.setPosition({ lineNumber, column: 1 });
    editor.focus();
  };

  // A new run restarts the hint progression for the new result. The chat
  // history is kept so the student can still refer to earlier feedback.
  const resetProgression = () => {
    setCurrentStage(null);
    setInput('');
    setHintError(null);
  };

  // Load an uploaded file into the editor.
  // Clearing the input afterwards lets the same file be uploaded again.
  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setCode(content);
      decorationsRef.current?.clear();
      setApiError(null);
    };
    reader.readAsText(file);

    event.target.value = '';
  };

  // Run the code in the sandbox and show the result.
  // The response is ignored if the session changed while waiting.
  const handleRun = async () => {
    // During the intro tour, show the sample result without calling the backend.
    if (isTourDemo) {
      setApiError(null);
      resetProgression();
      setResult({ ...getTourSample(editorLanguage.label).result });
      return;
    }
    if (!code.trim()) {
      setApiError('Please write some code before running it.');
      return;
    }
    if (!studentSession?.course) {
      setApiError('Please select your course before debugging.');
      navigate('/student/sessions');
      return;
    }
    const requestSessionId = sessionId;
    setIsLoading(true);
    setApiError(null);
    resetProgression();
    try {
      const response = await executeCode(
        code,
        studentSession?.course,
        studentSession?.language || editorLanguage.label,
        requestSessionId ?? undefined,
      );
      if (sessionIdRef.current !== requestSessionId) return;
      setResult(response);
      // Keep the code and result so the session can be continued from here.
      if (isSynced && requestSessionId) {
        saveSessionState(requestSessionId, code, response).catch(() => { });
      }
      // Mark where the new feedback starts so it reads as a continuation of
      // the conversation rather than a replacement.
      setMessages((prev) => (prev.length > 0 ? [...prev, { role: 'event', text: describeRun(response) }] : prev));
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setApiError(err instanceof Error ? err.message : 'Failed to reach the backend.');
      setResult(null);
    } finally {
      if (sessionIdRef.current === requestSessionId) setIsLoading(false);
    }
  };

  // Starts the intro tour. With an empty editor it runs as a demo and puts in
  // sample code to try. Code the student has written is never replaced.
  const startTour = () => {
    const demo = !code.trim();
    const sample = getTourSample(editorLanguage.label);
    setIsTourDemo(demo);
    if (demo) setResult(null);
    tourRef.current = startStudentTour({
      languageLabel: editorLanguage.label,
      extension: editorLanguage.extension,
      demo,
      onLoadSample: () => setCode(sample.code),
      // Remove the sample code and its made-up result so the student starts
      // fresh. Code the student typed over the sample is left alone.
      onEnd: () => {
        tourRef.current = null;
        if (!demo) return;
        setIsTourDemo(false);
        setCode((current) => (current === sample.code ? '' : current));
        setResult(null);
        decorationsRef.current?.clear();
      },
    });
  };

  // Start the tour by itself the first time a student account opens the
  // Student View. It waits until the saved session has loaded, so the editor
  // already shows any saved code when the tour picks demo or describe-only.
  // The ref stops it starting twice when React runs effects twice in development.
  const autoTourStartedRef = useRef(false);
  useEffect(() => {
    if (location.pathname !== '/student' || !isSynced) return;
    if (autoTourStartedRef.current || hasSeenTour(authSession, 'student')) return;
    autoTourStartedRef.current = true;
    startTour();
    // Only re-checked when the page, login or loaded session changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, isSynced, authSession]);

  // Builds the Finding the hints endpoint expects from the current execution result.
  const buildFinding = (execution: ExecutionResponse): Finding => ({
    error_type: execution.error!.error_type,
    line_number: execution.error!.line_number,
    failing_code_snippet: execution.error!.code_snippet ?? '',
  });

  // Turns one hint from the backend into a chat message, keeping the
  // resource details so the chat can show the link and the gate state.
  const toAssistantMessage = (hint: HintStage): ChatMessage => ({
    role: 'assistant',
    text: hint.text ?? '',
    stage: hint.stage,
    resourceUrl: hint.resource_url,
    resourceLabel: hint.resource_label,
    gated: hint.gate_on_url,
  });

  // Opens the conversation. There is no student message to classify yet, so
  // the backend just returns the stage 1 hint.
  const handleGetHint = async () => {
    if (!result?.error || result.error_id == null) return;
    const requestSessionId = sessionId;
    setIsHintLoading(true);
    setHintError(null);
    try {
      const response = await getHint(result.error_id, buildFinding(result), result);
      if (sessionIdRef.current !== requestSessionId) return;
      const first = response.hints[0];
      if (first?.text) {
        setMessages((prev) => [...prev, toAssistantMessage(first)]);
        setCurrentStage(first.stage);
      } else {
        setHintError('No hint came back. Try again in a moment.');
      }
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setHintError(err instanceof Error ? err.message : 'Failed to get a hint.');
    } finally {
      if (sessionIdRef.current === requestSessionId) setIsHintLoading(false);
    }
  };

  // Socratic mode: one call that returns the diagnosis and fix.
  const handleGetAnswer = async () => {
    if (!result?.error || result.error_id == null) return;
    const requestSessionId = sessionId;
    setIsHintLoading(true);
    setHintError(null);
    try {
      const response = await getHint(result.error_id, buildFinding(result), result, '', '', 'socratic');
      if (sessionIdRef.current !== requestSessionId) return;
      const answer = response.answer;
      if (answer && (answer.diagnosis || answer.fix)) {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', text: answer.fix ?? answer.diagnosis ?? '', answer, explanation: response.explanation },
        ]);
      } else {
        setHintError('No explanation came back. Try again in a moment.');
      }
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setHintError(err instanceof Error ? err.message : 'Failed to get an explanation.');
    } finally {
      if (sessionIdRef.current === requestSessionId) setIsHintLoading(false);
    }
  };

  const chooseHints = () => {
    setFeedbackMode('hints');
    setHasChosenMode(true);
    handleGetHint();
  };

  const chooseAnswer = () => {
    setFeedbackMode('socratic');
    setHasChosenMode(true);
    handleGetAnswer();
  };

  // The two choices offered on later runs. The last-used one is filled in.
  const hintChoiceButton = (lastUsed: boolean) => (
    <button type="button" className={`btn btn-primary ${lastUsed ? '' : 'btn-outline'}`} onClick={chooseHints}>
      <HandHelping size={16} />
      Give me a hint
    </button>
  );

  const answerChoiceButton = (lastUsed: boolean) => (
    <button type="button" className={`btn btn-primary ${lastUsed ? '' : 'btn-outline'}`} onClick={chooseAnswer}>
      <Lightbulb size={16} />
      Show me the answer
    </button>
  );

  // Sends the student's reply. The backend classifies it against the current
  // stage task and decides whether the stage advances - the stage itself is
  // never sent from here.
  const handleSend = async () => {
    if (sendDisabled) return;
    if (!result?.error || result.error_id == null) return;

    const studentText = input.trim();
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant' && !m.answer);
    const requestSessionId = sessionId;

    setMessages((prev) => [...prev, { role: 'student', text: studentText }]);
    setInput('');
    setIsHintLoading(true);
    setHintError(null);

    try {
      const response = await getHint(
        result.error_id,
        buildFinding(result),
        result,
        studentText,
        lastAssistant?.text ?? '',
      );
      if (sessionIdRef.current !== requestSessionId) return;
      const next = response.hints[0];
      if (next?.text) {
        setMessages((prev) => [...prev, toAssistantMessage(next)]);
        setCurrentStage(next.stage);
      } else {
        // The endpoint returns 200 even when hint generation fails, so an
        // empty body has to be surfaced rather than rendered as a blank reply.
        setHintError('No response came back. Try sending that again.');
      }
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setHintError(err instanceof Error ? err.message : 'Failed to reach the assistant.');
    } finally {
      if (sessionIdRef.current === requestSessionId) setIsHintLoading(false);
    }
  };

  // Ends the session before signing out, so the next login starts a new one.
  const handleLogout = async () => {
    endSession();
    await signOut();
    navigate('/');
  };

  return (
    <Routes>
      <Route
        path="/student"
        element={
          <>
            <div className="student-debugger flex min-h-screen flex-col p-3 sm:p-5 xl:h-screen xl:min-h-[720px]">
              {/* Header: logo, title and profile menu */}
              <header className="navbar flex-row items-start gap-4 lg:items-center">
                <div className="flex flex-1 items-center gap-3">
                  <img
                    src={appLogo}
                    alt="Error Guide logo"
                    className="h-16 w-16 shrink-0 rounded-box object-contain sm:h-[88px] sm:w-[88px]"
                  />
                  <div className="min-w-0">
                    <h1 className="font-mono text-xl font-semibold leading-tight tracking-wide text-primary sm:text-2xl sm:tracking-wider lg:text-3xl">ERROR GUIDE</h1>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <p>Student View{selectedCourse ? ` | ${selectedCourse}` : ''}</p>
                    </div>
                  </div>
                </div>
                {/* Replays the intro tour. */}
                <button
                  type="button"
                  data-tour="help"
                  className="btn btn-circle btn-ghost h-15 w-15 self-start lg:self-auto"
                  onClick={startTour}
                  aria-label="Show the intro tour"
                  title="Show the intro tour"
                >
                  <CircleHelp size={28} />
                </button>
                {/* Profile menu: theme and log out */}
                <div className="dropdown dropdown-end self-start lg:self-auto">
                  <button
                    type="button"
                    tabIndex={0}
                    className="btn btn-circle btn-primary h-15 w-15"
                    aria-label="Open profile menu"
                  >
                    <User size={30} />
                  </button>

                  <div
                    ref={menuRef}
                    tabIndex={0}
                    className="dropdown-content z-20 mt-3 w-64 rounded-xl border border-base-300 bg-base-100 p-4 shadow-xl"
                  >
                    <div className="mb-4 flex items-center gap-3 border-b border-base-300 pb-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-content">
                        <User size={24} />
                      </div>
                      <div>
                        <div className="font-semibold">Student</div>
                        <div className="text-sm text-base-content/60">Student account</div>
                      </div>
                    </div>

                    <div className="mb-3 flex items-center justify-between">
                      <div>
                        <div className="font-medium">Theme</div>
                        <div className="text-sm text-base-content/60 btn-outline">
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

                    <button
                      type="button"
                      className="btn btn-outline btn-sm mb-3 w-full"
                      onClick={() => navigate('/student/sessions')}
                    >
                      <History size={16} />
                      My sessions
                    </button>
                    <button
                      type="button"
                      className="btn btn-error w-full"
                      onClick={handleLogout}
                    >
                      <LogOut size={16} />
                      Log out
                    </button>
                  </div>
                </div>
              </header>
              <button
                type="button"
                className="btn btn-ghost btn-sm mb-2 ml-1 self-start sm:ml-2"
                onClick={() => navigate('/student/sessions')}
              >
                <ArrowLeft size={16} />
                Back to Sessions
              </button>

              <main
                ref={mainRef}
                className={`grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,var(--left))_1.5rem_minmax(0,var(--right))] xl:grid-rows-[minmax(0,1fr)] xl:gap-0 ${isDragging ? 'cursor-col-resize select-none' : ''}`}
                style={{ '--left': `${split}fr`, '--right': `${100 - split}fr` } as React.CSSProperties}
              >
                {/* Left side: code editor and output */}
                <section className="flex flex-col gap-3 xl:min-h-0">
                  <div data-tour="editor" className="student-panel card flex h-[400px] min-h-0 flex-col overflow-hidden rounded-box border border-base-300 bg-base-200 shadow-sm sm:h-[480px] xl:h-auto xl:flex-[3]">
                    <div className="student-panel-header rounded-t-box flex h-14 shrink-0 items-center justify-between bg-base-300 px-4 py-2 text-s text-base-content/60">
                      <span className="flex items-center gap-2">
                        <img
                          src={editorLanguage.logo}
                          alt={`${editorLanguage.label} logo`}
                          className="h-7 w-7 object-contain"
                        />
                        {editorLanguage.label} Code
                      </span>
                      <div className="flex items-center gap-5">
                        <span>main.{editorLanguage.extension}</span>
                        {/* Pinned to the editor header so it is always in view next to the code it runs. */}
                        <button
                          type="button"
                          data-tour="run"
                          className="btn btn-primary btn-sm min-w-24 text-sm"
                          onClick={handleRun}
                          disabled={isLoading || isHintLoading}
                          aria-busy={isLoading}
                        >
                          {isLoading ? <span className="loading loading-spinner loading-xs"></span> : <Play size={14} fill="currentColor" />}
                          Run
                        </button>
                      </div>
                    </div>

                    <div className="student-editor-surface relative flex-1 bg-[#1e1e1e] rounded-b-box overflow-hidden border border-base-300">
                      <Editor
                        height="100%"
                        language={editorLanguage.monaco}
                        theme={theme === 'light' ? 'light' : 'vs-dark'}
                        value={code}
                        onChange={(value) => {
                          // Editing keeps the chat; only a new run moves the feedback on.
                          // The highlight goes, since the flagged line may no longer be the fault.
                          setCode(value || '');
                          decorationsRef.current?.clear();
                          setApiError(null);
                        }}
                        onMount={handleEditorMount}
                        options={{ minimap: { enabled: false }, fontSize: 14, automaticLayout: true }} />

                      {!code && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10">
                          <p className={`${theme === 'light' ? 'text-base-content/70' : 'text-white/70'} text-center px-6 mb-2 text-lg font-medium`}>Write your failing {editorLanguage.label} code here...</p>
                          <p className={`${theme === 'light' ? 'text-base-content/50' : 'text-white/50'} mb-4`}>or</p>
                          <input type="file" accept={`.${editorLanguage.extension}`} className="hidden" ref={fileInputRef} onChange={handleFileUpload} />
                          <button data-tour="upload" className="btn btn-primary pointer-events-auto" onClick={() => fileInputRef.current?.click()}>
                            <Upload size={16} />Upload .{editorLanguage.extension} File</button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Output: what the program printed, then the error if it crashed.
                      Styled like the editor above, including its theme background. */}
                  <div data-tour="output" className="student-panel card flex min-h-[220px] flex-col overflow-hidden rounded-box border border-base-300 bg-base-200 shadow-sm xl:min-h-0 xl:flex-[1]">
                    <h2 className="student-panel-header rounded-t-box flex items-center gap-2 px-4 py-2 bg-base-300 text-xs text-base-content/60">
                      <SquareTerminal size={14} />
                      Output
                    </h2>
                    <div
                      ref={outputRef}
                      role="log"
                      aria-label="Program output"
                      className={`student-output-surface flex-1 overflow-auto rounded-b-box border border-base-300 px-4 py-3 font-mono text-sm text-base-content ${theme === 'light' ? 'bg-white' : 'bg-[#1e1e1e]'}`}
                    >
                      {isLoading ? (
                        <p className="text-base-content/60">Running...</p>
                      ) : !result ? (
                        <p className="text-base-content/50">Run your code to see its output here.</p>
                      ) : (
                        <>
                          {result.stdout && <pre className="whitespace-pre-wrap break-words">{result.stdout}</pre>}
                          {/* A crash shows as "IndexError: list index out of range", the
                              last line of the traceback. The full traceback, with its
                              sandbox file paths, is more than a first-year needs. */}
                          {result.error ? (
                            <pre className="whitespace-pre-wrap break-words text-error">
                              {result.error.message ? `${result.error.error_type}: ${result.error.message}` : result.error.error_type}
                            </pre>
                          ) : (
                            result.stderr && <pre className="whitespace-pre-wrap break-words text-error">{result.stderr}</pre>
                          )}
                          {result.timed_out && (
                            // Warning yellow is unreadable as text on white, so it colours the icon only.
                            <p className="flex items-center gap-2">
                              <AlertTriangle size={14} className="shrink-0 text-warning" />
                              Program stopped: it ran longer than the time limit.
                            </p>
                          )}
                          {!result.stdout && !result.stderr && !result.timed_out && (
                            <p className="text-base-content/60">Program finished with no output.</p>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </section>

                {/* Divider between the panels. Drag to resize, double-click to reset.
                  Wide screens only, where they sit side by side. */}
                <div
                  role="separator"
                  data-tour="divider"
                  aria-orientation="vertical"
                  aria-label="Resize code and assistant panels"
                  aria-valuemin={minSplit}
                  aria-valuemax={maxSplit}
                  aria-valuenow={Math.round(split)}
                  title="Drag to resize. Double-click to reset."
                  className="group hidden cursor-col-resize touch-none items-center justify-center xl:flex"
                  onPointerDown={handleDividerPointerDown}
                  onPointerMove={handleDividerPointerMove}
                  onPointerUp={handleDividerPointerUp}
                  onPointerCancel={handleDividerPointerUp}
                  onDoubleClick={() => setSplit(defaultSplit)}
                >
                  <div
                    className={`h-full w-1 rounded-full transition-colors ${isDragging ? 'bg-primary' : 'bg-base-300 group-hover:bg-primary/60'}`}
                  />
                </div>

                {/* Right side: run results and hint chat */}
                <section className="flex h-[540px] min-h-0 flex-col sm:h-[620px] xl:h-auto">
                  <div data-tour="assistant" className="student-card card bg-base-200 shadow-sm flex-1 flex flex-col min-h-0 overflow-hidden border border-base-300">

                    <div className="student-panel-header flex h-14 shrink-0 flex-wrap items-center gap-2 rounded-t-box border-b border-base-300/50 bg-base-300 px-4 py-2">
                      <Sparkles className="mr-1 text-primary size-6" />
                      <h2 className="flex-1 font-semibold text-xl tracking-wider">LLM ASSISTANT</h2>
                    </div>

                    <div className="flex flex-1 min-h-0 flex-col gap-1 p-3 sm:p-4">

                      <div className="shrink-0">
                        {isLoading && <p className="text-sm opacity-70">Running your code...</p>}
                        {apiError && <p className="text-error text-sm">{apiError}</p>}

                        {result?.timed_out && (
                          <div className="alert alert-warning text-sm p-3">
                            <AlertTriangle size={18} className="shrink-0 my-auto" />
                            <span className="font-bold">Execution Timed Out:</span> Check for infinite loops.
                          </div>
                        )}

                        {result && !result.timed_out && !result.error && (
                          <div className="alert alert-success text-sm p-3">
                            <CheckCircle2 size={16} className="shrink-0 my-auto" />
                            <span className="font-bold my-auto">Execution Successful</span>
                          </div>
                        )}

                        {result?.error && (
                          <div data-tour="error" className="rounded-box border border-error/40 bg-error/10 px-3 py-2 text-sm" role="alert">
                            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
                                <AlertCircle size={17} className="shrink-0 text-error" />
                                <p className="text-xs font-semibold tracking-wide text-base-content/60">WHAT HAPPENED</p>
                                <p className="font-medium">{result.error.error_type}</p>
                                <p className="min-w-0 text-base-content/75">{result.error.message}</p>
                              </div>

                              <div className="ml-auto flex shrink-0 items-center gap-2">
                                <p className="text-xs font-semibold tracking-wide text-base-content/60">WHERE TO LOOK</p>
                                {result.error.line_number ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-error"
                                    onClick={() => focusErrorLine(result.error!.line_number!)}
                                  >
                                    Go to line {result.error.line_number}
                                  </button>
                                ) : (
                                  <p className="text-base-content/75">Review the code near the error.</p>
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="student-chat-surface flex-1 bg-base-100 rounded-box border border-base-300 flex flex-col overflow-hidden">

                        <div ref={messagesContainerRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-x-hidden overflow-y-auto p-3 sm:p-4">
                          {!result?.error && !isLoading && messages.length === 0 && (
                            <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-base opacity-50 sm:flex-row sm:text-lg">
                              <span>Submit code to see feedback here</span>
                              <SquareCode className='size-8 sm:size-9' />
                            </div>
                          )}

                          {messages.map((m, i) => {
                            if (m.role === 'event') {
                              return (
                                <div key={i} className="divider my-1 text-xs opacity-60">
                                  {m.text}
                                </div>
                              );
                            }

                            // Show the resource link only on the message that first offered it
                            // in this run, not on every follow-up while the gate is open.
                            const showResource =
                              m.resourceUrl &&
                              !messages.slice(runStartIndex(messages, i), i).some((p) => p.resourceUrl === m.resourceUrl);

                            return (
                              <div key={i} className={m.role === 'student' ? 'chat chat-end' : 'chat chat-start'}>
                                {m.role === 'assistant' && (
                                  <div className="chat-image avatar">
                                    <div className="w-8 rounded-full bg-primary text-primary-content flex items-center justify-center mr-2">
                                      <Bot size={20} />
                                    </div>
                                  </div>
                                )}
                                <div
                                  className={`chat-bubble max-w-full break-words text-sm shadow-sm ${m.role === 'student' ? 'chat-bubble-neutral' : 'chat-bubble-primary'
                                    }`}
                                >
                                  {m.answer ? (
                                    <div className="space-y-3">
                                      {m.answer.diagnosis && (
                                        <div>
                                          <div className="mb-1 border-b border-primary-content/20 pb-1 font-bold">What went wrong</div>
                                          <p className="whitespace-pre-wrap">{m.answer.diagnosis}</p>
                                        </div>
                                      )}
                                      {m.answer.fix && (
                                        <div>
                                          <div className="mb-1 border-b border-primary-content/20 pb-1 font-bold">How to fix it</div>
                                          <p className="whitespace-pre-wrap">{m.answer.fix}</p>
                                        </div>
                                      )}
                                    </div>
                                  ) : (
                                    m.text
                                  )}
                                </div>
                                {m.answer && <WhyThisHint explanation={m.explanation} />}
                                {showResource && (
                                  <a
                                    href={m.resourceUrl!}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="chat-footer mt-2 btn btn-sm btn-outline hover:btn-primary gap-2"
                                  >
                                    <BookOpen size={14} />
                                    {m.resourceLabel ?? 'Open learning resource'}
                                    <ExternalLink size={12} />
                                  </a>
                                )}
                                {m.role === 'student' && (
                                  <div className="chat-image avatar">
                                    <div className="w-8 rounded-full bg-neutral text-neutral-content flex items-center justify-center ml-2">
                                      <UserRound size={20} />
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}

                          {/* The choice is offered where the student asks for help, so
                              there is no separate setting to find first. */}
                          {result?.error && !helpChosen && !isHintLoading && !isLoading && !hasChosenMode && (
                            <div data-tour="help-choice" className="flex flex-col gap-2">
                              <p className="text-sm font-medium">How do you want help?</p>
                              <div className="grid gap-2 sm:grid-cols-2">
                                <button
                                  type="button"
                                  className="btn btn-primary h-auto flex-col items-start gap-1 py-3 text-left"
                                  onClick={chooseHints}
                                >
                                  <span className="flex items-center gap-2 font-semibold">
                                    <HandHelping size={16} />
                                    Give me a hint
                                  </span>
                                  <span className="text-xs font-normal opacity-80">Step by step, so you find the fix yourself</span>
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-primary h-auto flex-col items-start gap-1 py-3 text-left"
                                  onClick={chooseAnswer}
                                >
                                  <span className="flex items-center gap-2 font-semibold">
                                    <Lightbulb size={16} />
                                    Show me the answer
                                  </span>
                                  <span className="text-xs font-normal opacity-80">Explains the error and the fix straight away</span>
                                </button>
                              </div>
                            </div>
                          )}

                          {/* Later runs carry on with the last choice in one click, as the
                              old toggle did. A new run is when switching is allowed, so the
                              other mode sits beside it as a button too, with the last
                              choice first and filled in. */}
                          {result?.error && !helpChosen && !isHintLoading && !isLoading && hasChosenMode && (
                            <div data-tour="help-choice" className="flex flex-wrap gap-2">
                              {isSocratic ? (
                                <>
                                  {answerChoiceButton(true)}
                                  {hintChoiceButton(false)}
                                </>
                              ) : (
                                <>
                                  {hintChoiceButton(true)}
                                  {answerChoiceButton(false)}
                                </>
                              )}
                            </div>
                          )}

                          {/* Shown locked rather than hidden, so the student can see the
                              answer exists and how to get to it. */}
                          {result?.error && hintsInProgress && !isHintLoading && !isLoading && (
                            <div className="flex flex-wrap items-center gap-2 text-xs text-base-content/60">
                              <button type="button" className="btn btn-sm btn-outline" disabled>
                                <Lock size={14} />
                                Show me the answer
                              </button>
                              <span>Run your code again to switch to the answer.</span>
                            </div>
                          )}

                          {isHintLoading && <p className="text-sm opacity-70">Thinking...</p>}
                          {hintError && <p className="text-sm text-error">{hintError}</p>}

                          {!isSocratic && isFinalStage && (
                            <p className="text-xs opacity-60 text-center py-2">
                              That is the last hint for this error. Fix your code and run it again.
                            </p>
                          )}

                        </div>

                        <div data-tour="chat-input" className="student-chat-composer flex gap-2 bg-base-300 p-2">
                          <input
                            type="text"
                            className="input input-md flex-1 bg-base-100 font-medium focus:outline-none focus:border-primary"
                            placeholder={
                              answeredThisRun
                                ? 'Run your code again to get hints.'
                                : isFinalStage
                                  ? 'You have reached the last hint.'
                                  : 'Reply to the assistant...'
                            }
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                handleSend();
                              }
                            }}
                            disabled={currentStage === null || isLoading || isHintLoading || isFinalStage || isSocratic}
                          />
                          <button
                            className={`btn btn-primary ${sendDisabled ? 'pointer-events-none cursor-not-allowed' : ''}`}
                            onClick={handleSend}
                            disabled={sendDisabled}
                          >
                            {isHintLoading ? <span className="loading loading-spinner loading-sm"></span> : 'Send'}
                            <Send size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </section>
              </main>
            </div>
          </>
        }
      />
      <Route path="/" element={<WelcomePage />} />
      {/* Old login and register pages, now sent to the welcome page. */}
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/register" element={<Navigate to="/" replace />} />
      {/* Old setup page, replaced by the session history. */}
      <Route path="/student/setup" element={<Navigate to="/student/sessions" replace />} />
      {/* The student's saved sessions. Only for logged-in students. */}
      <Route
        path="/student/sessions"
        element={
          <ProtectedRoute>
            <SessionHistoryPage />
          </ProtectedRoute>
        }
      />
      {/* Instructor dashboard. Only for logged-in instructors. */}
      <Route
        path="/instructor"
        element={
          <ProtectedRoute>
            <InstructorDashboard onBack={handleLogout} />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
