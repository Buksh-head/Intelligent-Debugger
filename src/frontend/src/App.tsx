/**
 * Main app component. Sets up the page routes and contains the whole
 * student page: code editor, run results and the stage 1 hint. When a run
 * finishes without an error, the Expected behaviour tab lets the student
 * check its output against what they expected, and get hints if it differs.
 */
import { useEffect, useRef, useState } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import pythonLogo from "./assets/python.jpg";
import javaLogo from "./assets/java.jpg";
import javascriptLogo from "./assets/js.jpg";
import {
  Navigate,
  Routes,
  Route,
  useLocation,
  useNavigate,
} from "react-router-dom";
import InstructorDashboard from "./InstructorDashboard";
import WelcomePage from "./pages/WelcomePage";
import SessionHistoryPage from "./pages/SessionHistoryPage";
import ProtectedRoute from "./auth/ProtectedRoute";
import { useAuth } from "./auth/useAuth";
import { useStudentSession } from "./session/useStudentSession";
import {
  type HintStep,
  loadOrRegisterSession,
  restoreSession,
} from "./session/savedSession";
import type {
  ChatMessageRecord,
  ExecutionResponse,
  OutputCheck,
  SavedErrorRef,
  SocraticAnswer,
  Stage1Hint,
} from "./types";
import {
  getTourSample,
  startStudentTour,
  tourRunStep,
} from "./tour/studentTour";
import { hasSeenTour } from "./tour/tourStatus";
import type { Driver } from "driver.js";
import {
  appendChatMessages,
  checkOutput,
  executeCode,
  getSocraticAnswer,
  getStage1Hint,
  saveSessionState,
} from "./api";
import FollowUpHints from "./hints/FollowUpHints";
import ExpectedOutput from "./hints/ExpectedOutput";
import SocraticAnswerCard from "./hints/SocraticAnswerCard";
import axios from "axios";
import { type Theme, getInitialTheme, themeStorageKey } from "./theme";

import {
  ArrowLeft,
  LogOut,
  Upload,
  Play,
  SquareTerminal,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  HandHelping,
  SquareCode,
  Sun,
  Moon,
  User,
  Lightbulb,
  CircleHelp,
  History,
  ListChecks,
  KeyRound,
} from "lucide-react";

type MonacoEditor = Parameters<OnMount>[0];
type DecorationsCollection = ReturnType<
  MonacoEditor["createDecorationsCollection"]
>;

// Editor settings for each course. Used if the student didn't pick a language.
const courseEditorLanguages: Record<
  string,
  { monaco: string; label: string; extension: string; logo: string }
> = {
  CSSE1001: {
    monaco: "python",
    label: "Python",
    extension: "py",
    logo: pythonLogo,
  },
  CSSE2002: {
    monaco: "java",
    label: "Java",
    extension: "java",
    logo: javaLogo,
  },
  ENGG1001: {
    monaco: "python",
    label: "Python",
    extension: "py",
    logo: pythonLogo,
  },
  DECO1800: {
    monaco: "javascript",
    label: "JavaScript",
    extension: "js",
    logo: javascriptLogo,
  },
};

// Editor settings for each language the student can pick at setup.
const languageEditorLanguages: Record<
  string,
  { monaco: string; label: string; extension: string; logo: string }
> = {
  Python: {
    monaco: "python",
    label: "Python",
    extension: "py",
    logo: pythonLogo,
  },
  Java: { monaco: "java", label: "Java", extension: "java", logo: javaLogo },
  JavaScript: {
    monaco: "javascript",
    label: "JavaScript",
    extension: "js",
    logo: javascriptLogo,
  },
};

const appLogo = "/error-guide-logo.png";

// Width split between the code and assistant panels, as the left panel's
// share in percent. Saved per session so a new session starts at 50/50.
const splitStoragePrefix = "debugging-assistant.panel-split.";
const defaultSplit = 50;
const minSplit = 30;
const maxSplit = 70;

const clampSplit = (value: number) =>
  Math.min(maxSplit, Math.max(minSplit, value));

// This session's saved split, or the 50/50 default.
const getSavedSplit = (sessionId: string | null): number => {
  if (!sessionId) return defaultSplit;
  try {
    const saved = Number(
      sessionStorage.getItem(splitStoragePrefix + sessionId),
    );
    return saved > 0 ? clampSplit(saved) : defaultSplit;
  } catch {
    return defaultSplit; // storage can be blocked, the default still works
  }
};

// The message to show for a failed request: the backend's own explanation
// when it sent one (e.g. "Only Python code can be run for now."), otherwise
// the generic error text.
const requestErrorMessage = (err: unknown, fallback: string): string => {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string") return detail;
  }
  return err instanceof Error ? err.message : fallback;
};

function App() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  // Code and run results
  const [code, setCode] = useState("");
  // Text fed to input() calls when the program runs.
  const [stdin, setStdin] = useState("");
  // The code and input of the last run. The hint is about that run, even if
  // the student has edited the code since.
  const [ranCode, setRanCode] = useState("");
  const [ranStdin, setRanStdin] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ExecutionResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  // Stage 1 hint: one leading question about the error in the last run.
  // There is no chat; the student reads the question and goes back to the code.
  const [isHintLoading, setIsHintLoading] = useState(false);
  const [hint, setHint] = useState<Stage1Hint | null>(null);
  const [hintError, setHintError] = useState<string | null>(null);

  // Socratic mode: the whole answer (what went wrong and how to fix it) in one
  // turn, for a student who wants it instead of, or after, the hints.
  const [isAnswerLoading, setIsAnswerLoading] = useState(false);
  const [answer, setAnswer] = useState<SocraticAnswer | null>(null);
  const [answerError, setAnswerError] = useState<string | null>(null);

  // Logic errors: after a run that finished without an error, the student can
  // type the output they expected (the Expected behaviour tab) and check it.
  const [outputTab, setOutputTab] = useState<"output" | "expected">("output");
  const [expected, setExpected] = useState("");
  const [isChecking, setIsChecking] = useState(false);
  const [outputCheck, setOutputCheck] = useState<OutputCheck | null>(null);
  // The expected output that outputCheck (and any hint about it) is for.
  const [checkedExpected, setCheckedExpected] = useState("");
  const [checkError, setCheckError] = useState<string | null>(null);
  // Follow-ups restored with a saved hint, shown under it again.
  const [restoredSteps, setRestoredSteps] = useState<HintStep[]>([]);
  const [followUpComposerHost, setFollowUpComposerHost] =
    useState<HTMLDivElement | null>(null);

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

  const selectedCourse = studentSession?.course ?? "";

  // Editor language: the student's chosen language first, then their course's, then Python.
  const editorLanguage =
    languageEditorLanguages[studentSession?.language ?? ""] ??
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
    setCode("");
    setStdin("");
    setRanCode("");
    setRanStdin("");
    setIsLoading(false);
    setResult(null);
    setApiError(null);
    setIsHintLoading(false);
    setIsAnswerLoading(false);
    setHint(null);
    setAnswer(null);
    setHintError(null);
    setAnswerError(null);
    setOutputTab("output");
    setExpected("");
    setIsChecking(false);
    setOutputCheck(null);
    setCheckedExpected("");
    setCheckError(null);
    setRestoredSteps([]);
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
  // been loaded (or registered, if it is new), so earlier code is never
  // overwritten. If that fails, e.g. when the backend has no session storage,
  // the page still works but isn't saved.
  const isSynced = sessionId !== null && syncedSessionId === sessionId;

  // The session's saved hint conversation, so new messages get the next positions.
  const chatRef = useRef<ChatMessageRecord[]>([]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    chatRef.current = [];
    loadOrRegisterSession(
      sessionId,
      studentSession?.course ?? "",
      studentSession?.language ?? "",
    )
      .then((detail) => {
        if (cancelled) return;
        if (detail) {
          const restored = restoreSession(detail);
          chatRef.current = detail.messages;
          setCode(restored.code);
          setRanCode(restored.code);
          setStdin(restored.stdin);
          setRanStdin(restored.stdin);
          setResult(restored.result);
          setExpected(restored.expected);
          const finished =
            restored.result !== null &&
            restored.result.error === null &&
            !restored.result.timed_out;
          if (finished && restored.expected.trim()) setOutputTab("expected");
          if (restored.hint || restored.answer) {
            setHint(restored.hint);
            setAnswer(restored.answer);
            setRestoredSteps(restored.steps);
            setOutputCheck(restored.check);
            setCheckedExpected(restored.checkedExpected);
          } else if (finished && restored.result && restored.expected.trim()) {
            // No hint yet: show whether the last run matched again (quick, no model).
            const expectedText = restored.expected;
            setIsChecking(true);
            checkOutput(
              restored.code,
              restored.result.stdout,
              expectedText,
              sessionId,
              restored.result.submission_id,
            )
              .then((check) => {
                if (cancelled) return;
                setOutputCheck(check);
                setCheckedExpected(expectedText);
              })
              .catch(() => {})
              .finally(() => {
                if (!cancelled) setIsChecking(false);
              });
          }
        }
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

  const editorRef = useRef<MonacoEditor | null>(null);
  const decorationsRef = useRef<DecorationsCollection | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const outputRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const mainRef = useRef<HTMLElement | null>(null);
  const tourRef = useRef<Driver | null>(null);

  // The last run finished without an error, so its output can be checked.
  const ranOk = result !== null && result.error === null && !result.timed_out;
  // The output was checked and is not what the student expected.
  const isLogicError = ranOk && outputCheck !== null && !outputCheck.matches;
  // A hint can be asked for when the last run crashed, never finished, or
  // printed something other than what the student expected.
  const canAskForHint =
    result !== null &&
    (result.error !== null || result.timed_out || isLogicError);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
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

  // Reload the saved theme when the student page opens (the instructor
  // dashboard may have changed it). Done during render, like the session
  // reset above, so the page never paints in the old theme first.
  const [themePath, setThemePath] = useState(location.pathname);
  if (location.pathname !== themePath) {
    setThemePath(location.pathname);
    if (location.pathname === "/student") setTheme(getInitialTheme());
  }

  // Highlight the failing line in the editor whenever a new result with an
  // error comes back; clear it on a clean run or a fresh loading state.
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;

    decorationsRef.current?.clear();

    // Once there is a hint, highlight the line it points at, which can differ
    // from the line where Python stopped.
    const lineNumber = hint?.cause_line ?? result?.error?.line_number;
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
            className: "error-line-highlight",
          },
        },
      ]);
    }
  }, [result, hint]);

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
  const handleDividerPointerDown = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsDragging(true);
  };

  const handleDividerPointerMove = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    if (!isDragging) return;
    const main = mainRef.current;
    if (!main) return;
    const rect = main.getBoundingClientRect();
    setSplit(clampSplit(((event.clientX - rect.left) / rect.width) * 100));
  };

  const handleDividerPointerUp = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
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

  // A new run gets a fresh hint: the old one was about the old error.
  const resetProgression = () => {
    setHint(null);
    setAnswer(null);
    setHintError(null);
    setAnswerError(null);
    setRestoredSteps([]);
    setOutputCheck(null);
    setCheckError(null);
  };

  // Saves messages of the hint conversation to the student's account.
  // Nothing is saved before the session has loaded, or in the tour demo.
  const saveChat = (records: Omit<ChatMessageRecord, "position">[]) => {
    if (!isSynced || !sessionId || isTourDemo) return;
    const start = chatRef.current.length;
    const added = records.map((r, i) => ({ ...r, position: start + i }));
    chatRef.current = [...chatRef.current, ...added];
    appendChatMessages(sessionId, added).catch(() => {});
  };

  // A new run or output check starts a new conversation. The saved copy marks
  // where, so only the latest conversation is restored.
  const startNewConversation = () => {
    const last = chatRef.current[chatRef.current.length - 1];
    if (last && (last.body as { kind?: string }).kind !== "run") {
      saveChat([{ role: "event", body: { kind: "run", text: "New run" } }]);
    }
  };

  // Keeps the code, the run (with its input) and the expected output, so the
  // session can be continued from here.
  const saveState = (
    savedCode: string,
    run: ExecutionResponse | null,
    runStdin: string,
    expectedText: string,
  ) => {
    if (!isSynced || !sessionId || isTourDemo) return;
    saveSessionState(
      sessionId,
      savedCode,
      run ? { ...run, stdin: runStdin } : null,
      expectedText,
    ).catch(() => {});
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

    event.target.value = "";
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
      setApiError("Please write some code before running it.");
      return;
    }
    if (!studentSession?.course) {
      setApiError("Please select your course before debugging.");
      navigate("/student/sessions");
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
        stdin,
        expected,
      );
      if (sessionIdRef.current !== requestSessionId) return;
      setResult(response);
      setRanCode(code);
      setRanStdin(stdin);
      startNewConversation();
      const finished = response.error === null && !response.timed_out;
      if (!finished) setOutputTab("output");
      // The student already said what they expect: check the new output too,
      // so they can see straight away whether their change worked.
      if (finished && expected.trim() && !isTourDemo) {
        void runOutputCheck(code, response, expected);
      }
      saveState(code, response, stdin, expected);
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setApiError(requestErrorMessage(err, "Failed to reach the backend."));
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
    if (demo) {
      setResult(null);
      setHint(null);
      setAnswer(null);
    }
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
        setCode((current) => (current === sample.code ? "" : current));
        setResult(null);
        setHint(null);
        setAnswer(null);
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
    if (location.pathname !== "/student" || !isSynced) return;
    if (autoTourStartedRef.current || hasSeenTour(authSession, "student"))
      return;
    autoTourStartedRef.current = true;
    startTour();
    // Only re-checked when the page, login or loaded session changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, isSynced, authSession]);

  // Compares a finished run's output with what the student expected. Any
  // hint from before is about the old comparison, so it is cleared.
  // For a saved run, a difference is saved as a logic error for the dashboard.
  const runOutputCheck = async (
    ranWith: string,
    run: ExecutionResponse,
    expectedText: string,
  ) => {
    const requestSessionId = sessionId;
    setHint(null);
    setAnswer(null);
    setHintError(null);
    setAnswerError(null);
    setRestoredSteps([]);
    setCheckError(null);
    setIsChecking(true);
    try {
      const response = await checkOutput(
        ranWith,
        run.stdout,
        expectedText,
        requestSessionId ?? undefined,
        run.submission_id,
      );
      if (sessionIdRef.current !== requestSessionId) return;
      setOutputCheck(response);
      setCheckedExpected(expectedText);
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setOutputCheck(null);
      setCheckError(requestErrorMessage(err, "Failed to check your output."));
    } finally {
      if (sessionIdRef.current === requestSessionId) setIsChecking(false);
    }
  };

  const handleCheckOutput = () => {
    if (!result || !ranOk || !expected.trim()) return;
    startNewConversation();
    saveState(ranCode, result, ranStdin, expected);
    void runOutputCheck(ranCode, result, expected);
  };

  // The saved session and error the hints are about, so they are recorded
  // for the instructor dashboard.
  const savedError: SavedErrorRef = {
    session_id: sessionId ?? undefined,
    error_id: isLogicError ? outputCheck?.error_id : result?.error_id,
  };

  // Asks for the stage 1 hint: one leading question that points at the cause
  // of the error without giving the fix away.
  const handleGetHint = async () => {
    if (!result || !canAskForHint) return;
    // During the intro tour, show the sample hint without calling the backend.
    if (isTourDemo) {
      setHint(getTourSample(editorLanguage.label).hint);
      return;
    }
    const requestSessionId = sessionId;
    setIsHintLoading(true);
    setHintError(null);
    setAnswerError(null);
    const logic = isLogicError;
    try {
      const response = await getStage1Hint(
        ranCode,
        ranStdin,
        result,
        logic ? checkedExpected : undefined,
        savedError,
      );
      if (sessionIdRef.current !== requestSessionId) return;
      setHint(response);
      setRestoredSteps([]);
      saveChat([
        {
          role: "assistant",
          body: {
            kind: "hint",
            text: response.question,
            hint: response,
            check: logic ? outputCheck : null,
            expected: logic ? checkedExpected : null,
          },
        },
      ]);
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setHintError(requestErrorMessage(err, "Failed to get a hint."));
    } finally {
      if (sessionIdRef.current === requestSessionId) setIsHintLoading(false);
    }
  };

  // Socratic mode: asks for the whole answer, the diagnosis and the fix, with
  // how it was worked out. Available straight away, or after the hints.
  const handleGetAnswer = async () => {
    if (!result || !canAskForHint || isTourDemo) return;
    const requestSessionId = sessionId;
    setIsAnswerLoading(true);
    setAnswerError(null);
    const logic = isLogicError;
    try {
      const response = await getSocraticAnswer(
        ranCode,
        ranStdin,
        result,
        logic ? checkedExpected : undefined,
        savedError,
      );
      if (sessionIdRef.current !== requestSessionId) return;
      setAnswer(response);
      saveChat([
        {
          role: "assistant",
          body: {
            kind: "answer",
            text: [response.diagnosis, response.fix].filter(Boolean).join("\n\n"),
            answer: response,
            check: logic ? outputCheck : null,
            expected: logic ? checkedExpected : null,
          },
        },
      ]);
    } catch (err) {
      if (sessionIdRef.current !== requestSessionId) return;
      setAnswerError(requestErrorMessage(err, "Failed to get the answer."));
    } finally {
      if (sessionIdRef.current === requestSessionId) setIsAnswerLoading(false);
    }
  };

  // Ends the session before signing out, so the next login starts a new one.
  const handleLogout = async () => {
    endSession();
    await signOut();
    navigate("/");
  };

  return (
    <Routes>
      {/* Student page. Only for logged-in students. */}
      <Route
        path="/student"
        element={
          <ProtectedRoute requiredRole="student">
            <div className="student-debugger flex min-h-screen flex-col p-3 sm:p-5 lg:h-screen lg:min-h-180">
              {/* Header: logo, title and profile menu */}
              <header className="navbar flex-row items-start gap-4 lg:items-center">
                <div className="flex flex-1 items-center gap-3">
                  <img
                    src={appLogo}
                    alt="Error Guide logo"
                    className="h-16 w-16 shrink-0 rounded-box object-contain sm:h-22 sm:w-22"
                  />
                  <div className="min-w-0">
                    <h1 className="font-mono text-xl font-semibold leading-tight tracking-wide text-primary sm:text-2xl sm:tracking-wider lg:text-3xl">
                      ERROR GUIDE
                    </h1>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <p>
                        Student View
                        {selectedCourse ? ` | ${selectedCourse}` : ""}
                      </p>
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
                        <div className="text-sm text-base-content/60">
                          Student account
                        </div>
                      </div>
                    </div>

                    <div className="mb-3 flex items-center justify-between">
                      <div>
                        <div className="font-medium">Theme</div>
                        <div className="text-sm text-base-content/60 btn-outline">
                          {theme === "dark" ? "Dark mode" : "Light mode"}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn btn-sm btn-circle btn-outline"
                        onClick={() =>
                          setTheme(theme === "dark" ? "light" : "dark")
                        }
                        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
                      >
                        {theme === "dark" ? (
                          <Sun size={16} />
                        ) : (
                          <Moon size={16} />
                        )}
                      </button>
                    </div>

                    <button
                      type="button"
                      className="btn btn-outline btn-sm mb-3 w-full"
                      onClick={() => navigate("/student/sessions")}
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
                onClick={() => navigate("/student/sessions")}
              >
                <ArrowLeft size={16} />
                Back to Sessions
              </button>

              <main
                ref={mainRef}
                className={`grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,var(--left))_1.5rem_minmax(0,var(--right))] lg:grid-rows-[minmax(0,1fr)] lg:gap-0 ${isDragging ? "cursor-col-resize select-none" : ""}`}
                style={
                  {
                    "--left": `${split}fr`,
                    "--right": `${100 - split}fr`,
                  } as React.CSSProperties
                }
              >
                {/* Left side: code editor and output */}
                <section className="flex flex-col gap-3 lg:min-h-0">
                  <div
                    data-tour="editor"
                    className="student-panel card flex h-100 min-h-0 flex-col overflow-hidden rounded-box border border-base-300 bg-base-200 shadow-sm sm:h-120 lg:h-auto lg:flex-3"
                  >
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
                          disabled={isLoading || isHintLoading || isAnswerLoading}
                          aria-busy={isLoading}
                        >
                          {isLoading ? (
                            <span className="loading loading-spinner loading-xs"></span>
                          ) : (
                            <Play size={14} fill="currentColor" />
                          )}
                          Run
                        </button>
                      </div>
                    </div>

                    <div className="student-editor-surface relative flex-1 bg-[#1e1e1e] rounded-b-box overflow-hidden border border-base-300">
                      <Editor
                        height="100%"
                        language={editorLanguage.monaco}
                        theme={theme === "light" ? "light" : "vs-dark"}
                        value={code}
                        onChange={(value) => {
                          // Editing keeps the hint; only a new run moves the feedback on.
                          // The highlight goes, since the flagged line may no longer be the fault.
                          setCode(value || "");
                          decorationsRef.current?.clear();
                          setApiError(null);
                        }}
                        onMount={handleEditorMount}
                        options={{
                          minimap: { enabled: false },
                          fontSize: 14,
                          automaticLayout: true,
                        }}
                      />

                      {!code && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10">
                          <p
                            className={`${theme === "light" ? "text-base-content/70" : "text-white/70"} text-center px-6 mb-2 text-lg font-medium`}
                          >
                            Write your failing {editorLanguage.label} code
                            here...
                          </p>
                          <p
                            className={`${theme === "light" ? "text-base-content/50" : "text-white/50"} mb-4`}
                          >
                            or
                          </p>
                          <input
                            type="file"
                            accept={`.${editorLanguage.extension}`}
                            className="hidden"
                            ref={fileInputRef}
                            onChange={handleFileUpload}
                          />
                          <button
                            data-tour="upload"
                            className="btn btn-primary pointer-events-auto"
                            onClick={() => fileInputRef.current?.click()}
                          >
                            <Upload size={16} />
                            Upload .{editorLanguage.extension} File
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Text for input() calls. Collapsed by default, since many programs
                      need none; it opens by itself once there is some. */}
                  <details
                    data-tour="stdin"
                    className="student-panel rounded-box border border-base-300 bg-base-200 shadow-sm"
                    open={stdin !== "" || undefined}
                  >
                    <summary className="cursor-pointer px-4 py-2 text-xs text-base-content/60">
                      Input for your program (one line per input() call)
                    </summary>
                    <div className="px-3 pb-3">
                      <textarea
                        aria-label="Program input"
                        className="textarea textarea-bordered h-20 min-h-20 max-h-20 w-full resize-none overflow-y-auto rounded-lg font-mono text-sm"
                        rows={2}
                        placeholder="Type what you would enter when the program asks"
                        value={stdin}
                        onChange={(e) => setStdin(e.target.value)}
                      />
                    </div>
                  </details>

                  {/* Output: what the program printed, then the error if it crashed.
                      Styled like the editor above, including its theme background. */}
                  <div
                    data-tour="output"
                    className="student-panel card flex min-h-55 flex-col overflow-hidden rounded-box border border-base-300 bg-base-200 shadow-sm lg:min-h-0 lg:flex-1"
                  >
                    {/* The Expected behaviour tab appears once a run finishes
                        without an error, for checking the output (logic errors). */}
                    {ranOk && !isLoading && !isTourDemo ? (
                      <div
                        role="tablist"
                        aria-label="Output panel"
                        className="student-panel-header rounded-t-box flex items-center gap-1 px-2 py-1 bg-base-300 text-xs"
                      >
                        <button
                          type="button"
                          role="tab"
                          id="output-tab"
                          aria-selected={outputTab === "output"}
                          aria-controls="output-panel"
                          className={`flex items-center gap-2 rounded px-2 py-1 ${outputTab === "output" ? "bg-base-100 text-base-content" : "text-base-content/60 hover:text-base-content"}`}
                          onClick={() => setOutputTab("output")}
                        >
                          <SquareTerminal size={14} />
                          Output
                        </button>
                        <button
                          type="button"
                          role="tab"
                          id="expected-tab"
                          data-tour="expected-tab"
                          aria-selected={outputTab === "expected"}
                          aria-controls="expected-panel"
                          className={`flex items-center gap-2 rounded px-2 py-1 ${outputTab === "expected" ? "bg-base-100 text-base-content" : "text-base-content/60 hover:text-base-content"}`}
                          onClick={() => setOutputTab("expected")}
                        >
                          <ListChecks size={14} />
                          Expected behaviour
                        </button>
                      </div>
                    ) : (
                      <h2 className="student-panel-header rounded-t-box flex items-center gap-2 px-4 py-2 bg-base-300 text-xs text-base-content/60">
                        <SquareTerminal size={14} />
                        Output
                      </h2>
                    )}
                    {ranOk &&
                      !isLoading &&
                      !isTourDemo &&
                      outputTab === "expected" && (
                        <div
                          role="tabpanel"
                          id="expected-panel"
                          aria-labelledby="expected-tab"
                          className="flex flex-1 flex-col"
                        >
                          <ExpectedOutput
                            value={expected}
                            onChange={setExpected}
                            onCheck={handleCheckOutput}
                            isChecking={isChecking}
                            theme={theme}
                          />
                        </div>
                      )}
                    <div
                      id="output-panel"
                      hidden={
                        ranOk &&
                        !isLoading &&
                        !isTourDemo &&
                        outputTab === "expected"
                      }
                      ref={outputRef}
                      role="log"
                      aria-label="Program output"
                      className={`student-output-surface flex-1 overflow-auto rounded-b-box border border-base-300 px-4 py-3 font-mono text-sm text-base-content ${theme === "light" ? "bg-white" : "bg-[#1e1e1e]"}`}
                    >
                      {isLoading ? (
                        <p className="text-base-content/60">Running...</p>
                      ) : !result ? (
                        <p className="text-base-content/50">
                          Run your code to see its output here.
                        </p>
                      ) : (
                        <>
                          {result.stdout && (
                            <pre className="whitespace-pre-wrap wrap-break-word">
                              {result.stdout}
                            </pre>
                          )}
                          {/* A crash shows as "IndexError: list index out of range", the
                              last line of the traceback. The full traceback, with its
                              sandbox file paths, is more than a first-year needs. */}
                          {result.error ? (
                            <pre className="whitespace-pre-wrap wrap-break-word text-error">
                              {result.error.message
                                ? `${result.error.error_type}: ${result.error.message}`
                                : result.error.error_type}
                            </pre>
                          ) : (
                            result.stderr && (
                              <pre className="whitespace-pre-wrap wrap-break-word text-error">
                                {result.stderr}
                              </pre>
                            )
                          )}
                          {result.timed_out && (
                            // Warning yellow is unreadable as text on white, so it colours the icon only.
                            <p className="flex items-center gap-2">
                              <AlertTriangle
                                size={14}
                                className="shrink-0 text-warning"
                              />
                              Program stopped: it ran longer than the time
                              limit.
                            </p>
                          )}
                          {!result.stdout &&
                            !result.stderr &&
                            !result.timed_out && (
                              <p className="text-base-content/60">
                                Program finished with no output.
                              </p>
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
                  aria-label="Resize code and hint panels"
                  aria-valuemin={minSplit}
                  aria-valuemax={maxSplit}
                  aria-valuenow={Math.round(split)}
                  title="Drag to resize. Double-click to reset."
                  className="group hidden cursor-col-resize touch-none items-center justify-center lg:flex"
                  onPointerDown={handleDividerPointerDown}
                  onPointerMove={handleDividerPointerMove}
                  onPointerUp={handleDividerPointerUp}
                  onPointerCancel={handleDividerPointerUp}
                  onDoubleClick={() => setSplit(defaultSplit)}
                >
                  <div
                    className={`h-full w-1 rounded-full transition-colors ${isDragging ? "bg-primary" : "bg-base-300 group-hover:bg-primary/60"}`}
                  />
                </div>

                {/* Right side: run results and the stage 1 hint */}
                <section className="flex h-135 min-h-0 flex-col sm:h-155 lg:h-auto">
                  <div
                    data-tour="assistant"
                    className="student-card card bg-base-200 shadow-sm flex-1 flex flex-col min-h-0 overflow-hidden border border-base-300"
                  >
                    <div className="student-panel-header flex h-14 shrink-0 items-center gap-2 rounded-t-box border-b border-base-300/50 bg-base-300 px-4 py-2">
                      <Sparkles className="shrink-0 text-primary size-6" />
                      <h2 className="font-semibold text-xl tracking-wider">
                        HINTS
                      </h2>
                    </div>

                    <div className="flex flex-1 min-h-0 flex-col gap-1 p-3 sm:p-4">
                      <div className="shrink-0">
                        {isLoading && (
                          <p className="text-sm opacity-70">
                            Running your code...
                          </p>
                        )}
                        {apiError && (
                          <p className="text-error text-sm">{apiError}</p>
                        )}

                        {result?.timed_out && (
                          <div className="alert alert-warning text-sm p-3">
                            <AlertTriangle
                              size={18}
                              className="shrink-0 my-auto"
                            />
                            <span className="font-bold">
                              Execution Timed Out:
                            </span>{" "}
                            Check for infinite loops.
                          </div>
                        )}

                        {ranOk && !isLogicError && (
                          <div className="alert alert-success text-sm p-3">
                            <CheckCircle2
                              size={16}
                              className="shrink-0 my-auto"
                            />
                            <span className="font-bold my-auto">
                              {outputCheck?.matches
                                ? "Your output matches what you expected"
                                : "Execution Successful"}
                            </span>
                          </div>
                        )}

                        {/* A logic error: the program ran, but its output is not
                            what the student expected. */}
                        {isLogicError && outputCheck && (
                          <div
                            data-tour="logic-error"
                            className="rounded-box border border-warning/50 bg-warning/10 px-3 py-2 text-sm"
                            role="alert"
                          >
                            <div className="flex min-w-0 items-start gap-2">
                              <AlertTriangle
                                size={17}
                                className="mt-0.5 shrink-0 text-warning"
                              />
                              <div className="min-w-0">
                                <p className="text-xs font-semibold tracking-wide text-base-content/60">
                                  WHAT HAPPENED
                                </p>
                                <p className="font-medium">
                                  {outputCheck.title}
                                </p>
                                <p className="text-base-content/75">
                                  {outputCheck.message}
                                </p>
                              </div>
                            </div>
                          </div>
                        )}
                        {isChecking && (
                          <p className="flex items-center gap-2 text-sm opacity-70">
                            <span className="loading loading-dots loading-sm"></span>
                            Checking your output...
                          </p>
                        )}
                        {checkError && (
                          <p className="text-sm text-error">{checkError}</p>
                        )}

                        {result?.error && (
                          <div
                            data-tour="error"
                            className="rounded-box border border-error/40 bg-error/10 px-3 py-2 text-sm"
                            role="alert"
                          >
                            <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
                              {/* The error in plain English for beginners. Python's own
                                  message stays in the Output panel, like a real terminal. */}
                              <div className="flex min-w-0 flex-1 items-start gap-2">
                                <AlertCircle
                                  size={17}
                                  className="mt-0.5 shrink-0 text-error"
                                />
                                <div className="min-w-0">
                                  <p className="text-xs font-semibold tracking-wide text-base-content/60">
                                    WHAT HAPPENED
                                  </p>
                                  <p className="font-medium">
                                    {result.error.friendly_title ??
                                      result.error.error_type}
                                  </p>
                                  <p className="text-base-content/75">
                                    {result.error.friendly_message ??
                                      result.error.message}
                                  </p>
                                </div>
                              </div>

                              <div className="ml-auto flex shrink-0 flex-col items-start gap-2">
                                <p className="text-xs font-semibold tracking-wide text-base-content/60">
                                  WHERE TO LOOK
                                </p>
                                {result.error.line_number ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-error"
                                    onClick={() =>
                                      focusErrorLine(result.error!.line_number!)
                                    }
                                  >
                                    Go to line {result.error.line_number}
                                  </button>
                                ) : (
                                  <p className="text-base-content/75">
                                    Review the code near the error.
                                  </p>
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="student-chat-surface flex-1 bg-base-100 rounded-box border border-base-300 flex flex-col overflow-hidden">
                        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-x-hidden overflow-y-auto p-3 sm:p-4">
                          {!canAskForHint &&
                            !isLoading &&
                            !(
                              ranOk &&
                              !isTourDemo &&
                              !outputCheck?.matches
                            ) && (
                              <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-base opacity-50 sm:flex-row sm:text-lg">
                                <span>
                                  {outputCheck?.matches
                                    ? "It prints exactly what you expected. Nice work."
                                    : result
                                      ? "No errors to look at. Nice work."
                                      : "Run your code to see feedback here"}
                                </span>
                                <SquareCode className="size-8 sm:size-9" />
                              </div>
                            )}

                          {/* The run finished, but has the output been checked yet?
                              Logic errors don't stop the program, so ask. */}
                          {ranOk &&
                            !isTourDemo &&
                            !outputCheck &&
                            !isChecking &&
                            !isLoading && (
                              <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
                                <p className="text-base opacity-50 sm:text-lg">
                                  No errors to look at. Nice work.
                                </p>
                                <p className="text-sm">
                                  Some mistakes don&apos;t stop a program. Does
                                  it print what you expected?
                                </p>
                                <button
                                  type="button"
                                  className="btn btn-sm btn-outline btn-primary"
                                  onClick={() => setOutputTab("expected")}
                                >
                                  <ListChecks size={16} />
                                  Check against what I expected
                                </button>
                              </div>
                            )}

                          {/* Help is a leading question, or (Socratic mode) the whole
                              answer for a student who wants it straight away. */}
                          {canAskForHint &&
                            !hint &&
                            !answer &&
                            !isHintLoading &&
                            !isAnswerLoading &&
                            !isLoading && (
                              <div
                                data-tour="help-choice"
                                className="flex flex-col gap-2"
                              >
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    onClick={handleGetHint}
                                  >
                                    <HandHelping size={16} />
                                    Give me a hint
                                  </button>
                                  {!isTourDemo && (
                                    <button
                                      type="button"
                                      className="btn btn-outline btn-primary"
                                      onClick={handleGetAnswer}
                                    >
                                      <KeyRound size={16} />
                                      Show me the answer
                                    </button>
                                  )}
                                </div>
                                <p className="text-xs text-base-content/60">
                                  {isLogicError
                                    ? "A hint is a question about where your output starts to go differently, so you can find the mistake yourself."
                                    : "A hint is a question that points you towards the problem, so you can find the fix yourself."}
                                  {!isTourDemo &&
                                    " The answer tells you what went wrong and how to fix it."}
                                </p>
                              </div>
                            )}

                          {hint && (
                            <div
                              data-tour="hint"
                              className="rounded-box border border-primary/40 bg-primary/10 p-4"
                            >
                              <p className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wide text-primary">
                                <Lightbulb size={16} />
                                HINT 1: A QUESTION TO THINK ABOUT
                              </p>
                              {hint.category_label && (
                                <p className="mb-2">
                                  <span className="badge badge-sm badge-outline">
                                    Looks like {hint.category_label}
                                  </span>
                                </p>
                              )}
                              <p className="text-base leading-relaxed sm:text-lg">
                                {hint.question}
                              </p>
                              <div className="mt-4 flex flex-wrap items-center gap-3">
                                {hint.cause_line && (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-outline btn-primary"
                                    onClick={() =>
                                      focusErrorLine(hint.cause_line!)
                                    }
                                  >
                                    Look at line {hint.cause_line}
                                  </button>
                                )}
                                <p className="text-xs text-base-content/60">
                                  Check what the question asks, change your
                                  code, then run it again.
                                </p>
                              </div>
                            </div>
                          )}

                          {/* Stage 2: the student can answer the question and get a
                              follow-up question or a short answer. Not in the tour demo,
                              whose hint is made up. */}
                          {hint && result && !isTourDemo && (
                            <FollowUpHints
                              key={`${ranCode}\n${hint.question}`}
                              code={ranCode}
                              stdin={ranStdin}
                              execution={result}
                              firstQuestion={hint.question}
                              expected={
                                isLogicError ? checkedExpected : undefined
                              }
                              saved={savedError}
                              initialSteps={restoredSteps}
                              composerHost={followUpComposerHost}
                              onStep={(step) =>
                                saveChat([
                                  {
                                    role: "student",
                                    body: { kind: "reply", text: step.reply },
                                  },
                                  {
                                    role: "assistant",
                                    body: {
                                      kind: "followup",
                                      text: step.response.text,
                                      followup: step.response,
                                    },
                                  },
                                ])
                              }
                              onShowAnswer={
                                !answer && !isAnswerLoading && canAskForHint
                                  ? handleGetAnswer
                                  : undefined
                              }
                              onLookAtLine={focusErrorLine}
                              errorMessage={requestErrorMessage}
                            />
                          )}

                          {answer && (
                            <SocraticAnswerCard
                              answer={answer}
                              onLookAtLine={focusErrorLine}
                            />
                          )}

                          {isHintLoading && (
                            <p className="flex items-center gap-2 text-sm opacity-70">
                              <span className="loading loading-dots loading-sm"></span>
                              Thinking of a good question...
                            </p>
                          )}
                          {hintError && (
                            <p className="text-sm text-error">{hintError}</p>
                          )}
                          {isAnswerLoading && (
                            <p className="flex items-center gap-2 text-sm opacity-70">
                              <span className="loading loading-dots loading-sm"></span>
                              Working out the answer...
                            </p>
                          )}
                          {answerError && (
                            <p className="text-sm text-error">{answerError}</p>
                          )}
                        </div>
                        <div ref={setFollowUpComposerHost} className="shrink-0" />
                      </div>
                    </div>
                  </div>
                </section>
              </main>
            </div>
          </ProtectedRoute>
        }
      />
      <Route path="/" element={<WelcomePage />} />
      {/* Old login and register pages, now sent to the welcome page. */}
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/register" element={<Navigate to="/" replace />} />
      {/* Old setup page, replaced by the session history. */}
      <Route
        path="/student/setup"
        element={<Navigate to="/student/sessions" replace />}
      />
      {/* The student's saved sessions. Only for logged-in students. */}
      <Route
        path="/student/sessions"
        element={
          <ProtectedRoute requiredRole="student">
            <SessionHistoryPage />
          </ProtectedRoute>
        }
      />
      {/* Instructor dashboard. Only for logged-in instructors. */}
      <Route
        path="/instructor"
        element={
          <ProtectedRoute requiredRole="instructor">
            <InstructorDashboard onBack={handleLogout} />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
