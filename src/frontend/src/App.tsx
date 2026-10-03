import { useEffect, useRef, useState } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import pythonLogo from './assets/python.jpg';
import javaLogo from './assets/java.jpg';
import javascriptLogo from './assets/js.jpg';
import { Navigate, Routes, Route, useNavigate } from 'react-router-dom';
import InstructorDashboard from './InstructorDashboard'
import StudentSetupPage from './pages/StudentSetupPage';
import WelcomePage from './pages/WelcomePage';
import ProtectedRoute from './auth/ProtectedRoute';
import { useAuth } from './auth/useAuth';
import { useStudentSession } from './session/useStudentSession';
import type { ExecutionResponse, Finding, HintStage } from './types';
import { deleteStudentData, executeCode, getHint } from './api';

import {
  LogOut,
  Upload,
  BugPlay,
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
  Copy,
  Check,
  Trash2,
} from 'lucide-react';

type MonacoEditor = Parameters<OnMount>[0];
type DecorationsCollection = ReturnType<MonacoEditor['createDecorationsCollection']>;

type ChatMessage = {
  role: 'student' | 'assistant' | 'event'; // 'event' marks a resubmission within the chat
  text: string;
  stage?: number;
  resourceUrl?: string | null;   // link from the curated list, if this message offers one
  resourceLabel?: string | null; // the link's title
  gated?: boolean;               // true while the student still owes the check answer
};

const courseEditorLanguages: Record<string, { monaco: string; label: string; extension: string; logo: string }> = {
  CSSE1001: { monaco: 'python', label: 'Python', extension: 'py', logo: pythonLogo },
  CSSE2002: { monaco: 'java', label: 'Java', extension: 'java', logo: javaLogo },
  ENGG1001: { monaco: 'python', label: 'Python', extension: 'py', logo: pythonLogo },
  DECO1800: { monaco: 'javascript', label: 'JavaScript', extension: 'js', logo: javascriptLogo },
};

const themeOptions = [
  { label: 'Light', value: 'light' },
  { label: 'Dark', value: 'dark' },
  { label: 'Synthwave', value: 'synthwave' },
  { label: 'Forest', value: 'forest' },
  { label: 'Luxury', value: 'luxury' },
] as const;

type Theme = (typeof themeOptions)[number]['value'];
const themeStorageKey = 'debugging-assistant.theme';

const getInitialTheme = (): Theme => {
  const savedTheme = localStorage.getItem(themeStorageKey);
  const savedOption = themeOptions.find((option) => option.value === savedTheme);
  if (savedOption) return savedOption.value;

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
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
  const [code, setCode] = useState('');
  const [expectedBehavior, setExpectedBehavior] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<ExecutionResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const [isHintLoading, setIsHintLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [currentStage, setCurrentStage] = useState<number | null>(null);
  const [hintError, setHintError] = useState<string | null>(null);
  const [idCopied, setIdCopied] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const navigate = useNavigate();
  const { signOut } = useAuth();
  const { session: studentSession, endSession } = useStudentSession();
  const sessionId = studentSession?.id ?? null;

  const selectedCourse = studentSession?.course ?? '';
  const editorLanguage = courseEditorLanguages[selectedCourse] ?? courseEditorLanguages.CSSE1001;

  // Everything below is scoped to one session. When the session changes
  // (logout, or a new start from the welcome page) it is discarded so none of
  // it can show up in the next session. Adjusting state during render rather
  // than in an effect avoids painting the old chat for a frame.
  const [stateSessionId, setStateSessionId] = useState(sessionId);
  if (sessionId !== stateSessionId) {
    setStateSessionId(sessionId);
    setCode('');
    setExpectedBehavior('');
    setIsLoading(false);
    setResult(null);
    setApiError(null);
    setIsHintLoading(false);
    setMessages([]);
    setInput('');
    setCurrentStage(null);
    setHintError(null);
    setIdCopied(false);
    setConfirmingDelete(false);
    setIsDeleting(false);
    setDeleteError(null);
  }

  // Requests still in flight when the session changes must not write into the
  // next one. Handlers compare against this once their request resolves.
  const sessionIdRef = useRef(sessionId);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const editorRef = useRef<MonacoEditor | null>(null);
  const decorationsRef = useRef<DecorationsCollection | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // The final stage reveals the answer, so there is nothing further to unlock.
  const isFinalStage = currentStage === 5;

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(themeStorageKey, theme);
  }, [theme]);

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

  const handleEditorMount: OnMount = (editor) => {
    editorRef.current = editor;
  };

  // A new run restarts the hint progression for the new result. The chat
  // history is kept so the student can still refer to earlier feedback.
  const resetProgression = () => {
    setCurrentStage(null);
    setInput('');
    setHintError(null);
  };

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

  const handleDebug = async () => {
    if (!code.trim()) {
      setApiError('Please write some code before debugging.');
      return;
    }
    const requestSessionId = sessionId;
    setIsLoading(true);
    setApiError(null);
    resetProgression();
    try {
      const response = await executeCode(
        code,
        expectedBehavior,
        studentSession?.course,
        studentSession?.language || editorLanguage.label,
        requestSessionId ?? undefined,
      );
      if (sessionIdRef.current !== requestSessionId) return;
      setResult(response);
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

  // Sends the student's reply. The backend classifies it against the current
  // stage task and decides whether the stage advances - the stage itself is
  // never sent from here.
  const handleSend = async () => {
    if (!input.trim() || isHintLoading || isFinalStage || currentStage === null) return;
    if (!result?.error || result.error_id == null) return;

    const studentText = input.trim();
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
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

  // Copies the session ID so the student can delete this session's data
  // later, after the ID has gone from the browser
  const handleCopySessionId = async () => {
    if (!sessionId) return;
    try {
      await navigator.clipboard.writeText(sessionId);
      setIdCopied(true);
      setTimeout(() => setIdCopied(false), 2000);
    } catch {
      // Clipboard can be blocked, the ID is still shown for manual copying.
    }
  };

  // Deletes everything stored for this session, then ends it, so later runs
  // aren't saved under the ID that was just cleared.
  const handleDeleteData = async () => {
    if (!sessionId) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteStudentData(sessionId);
      await handleLogout();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Could not delete your data. Try again.');
      setIsDeleting(false);
    }
  };

  return (
    <Routes>
      <Route
        path="/student"
        element={
          <>
            <div className="flex min-h-screen flex-col p-3 sm:p-5">
              <header className="navbar mb-4 flex-col items-stretch gap-4 lg:flex-row lg:items-center">
                <div className="flex flex-1 items-center gap-3">
                  <img
                    src={editorLanguage.logo}
                    alt={`${editorLanguage.label} logo`}
                    className="h-10 shrink-0 sm:h-[50px]"
                  />
                  <div className="min-w-0">
                    <h1 className="font-mono text-xl font-semibold leading-tight tracking-wide text-primary sm:text-2xl sm:tracking-wider lg:text-3xl">INTELLIGENT {editorLanguage.label.toUpperCase()} DEBUGGER</h1>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <p>Student View{selectedCourse ? ` | ${selectedCourse}` : ''}</p>
                      {sessionId && (
                        <button
                          type="button"
                          onClick={handleCopySessionId}
                          className="badge badge-outline gap-1 font-mono text-xs cursor-pointer"
                          title="Click to copy your full session ID"
                        >
                          Session {sessionId.slice(0, 8)}…
                          {idCopied ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
                <div className="dropdown dropdown-end">
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
                    <div className="mb-3 border-b border-base-300 pb-3">
                      <div className="font-medium">Session ID</div>
                      <div className="mt-1 flex items-center gap-2">
                        <code className="flex-1 truncate rounded bg-base-200 px-2 py-1 text-xs" title={sessionId ?? ''}>
                          {sessionId ?? 'No active session'}
                        </code>
                        <button
                          type="button"
                          className="btn btn-xs btn-ghost"
                          onClick={handleCopySessionId}
                          disabled={!sessionId}
                          aria-label="Copy session ID"
                        >
                          {idCopied ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                      </div>
                      <p className="mt-1 text-xs text-base-content/60">
                        Keep this to delete this session's data after you log out.
                      </p>
                    </div>

                    {confirmingDelete ? (
                      <div className="mb-3 rounded-lg border border-error/40 p-3">
                        <p className="mb-2 text-sm">
                          Delete your code, errors and hints from this session? This can't be undone.
                        </p>
                        {deleteError && <p className="mb-2 text-xs text-error">{deleteError}</p>}
                        <div className="flex gap-2">
                          <button
                            type="button"
                            className="btn btn-sm flex-1"
                            onClick={() => {
                              menuRef.current?.focus();
                              setConfirmingDelete(false);
                              setDeleteError(null);
                            }}
                            disabled={isDeleting}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-error flex-1"
                            onClick={handleDeleteData}
                            disabled={isDeleting}
                          >
                            {isDeleting ? <span className="loading loading-spinner loading-xs"></span> : 'Delete'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-outline btn-sm mb-3 w-full"
                        onClick={() => {
                          menuRef.current?.focus();
                          setConfirmingDelete(true);
                        }}
                        disabled={!sessionId || isLoading || isHintLoading}
                      >
                        <Trash2 size={16} />
                        Delete my data
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-outline btn-error w-full"
                      onClick={handleLogout}
                    >
                      <LogOut size={16} />
                      Log out
                    </button>
                  </div>
                </div>
              </header>

              <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-2 xl:gap-6">
                <section className="flex flex-col gap-3 xl:min-h-0">
                  <div className="flex h-[400px] min-h-0 flex-col sm:h-[480px] xl:h-auto xl:flex-[3]">
                    <div className="rounded-t-box flex justify-between items-center px-4 py-2 bg-base-300 text-xs text-base-content/60">
                      <span>Your {editorLanguage.label} Code</span>
                      <div className="flex items-center gap-3">
                        <span>main.{editorLanguage.extension}</span>
                      </div>
                    </div>

                    <div className="relative flex-1 bg-[#1e1e1e] rounded-b-box overflow-hidden border border-base-300">
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
                        options={{ minimap: { enabled: false }, fontSize: 14 }}
                      />

                      {!code && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10">
                          <p className="text-white/70 text-center px-6 mb-2 text-lg font-medium">Write your failing {editorLanguage.label} code here...</p>
                          <p className="text-white/50 mb-4">or</p>
                          <input type="file" accept={`.${editorLanguage.extension}`} className="hidden" ref={fileInputRef} onChange={handleFileUpload} />
                          <button className="btn btn-outline btn-primary pointer-events-auto" onClick={() => fileInputRef.current?.click()}>
                            <Upload size={16} />Upload .{editorLanguage.extension} File</button>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex min-h-[220px] flex-col rounded-box bg-base-200 p-3 shadow-sm xl:min-h-0 xl:flex-[1]">
                    <h2 className="text-sm font-semibold tracking-wider mb-2">EXPECTED BEHAVIOUR (OPTIONAL)</h2>
                    <div className="flex-1 flex">
                      <textarea
                        className="textarea textarea-bordered border-base-300 w-full flex-1 resize-none focus:outline-none focus:border-primary"
                        placeholder="Explain what your code is supposed to do..."
                        value={expectedBehavior}
                        onChange={(e) => setExpectedBehavior(e.target.value)}
                      />
                    </div>
                    <button className="btn btn-outline btn-primary pointer-events-auto mt-2 h-11 w-full" onClick={handleDebug} disabled={isLoading || isHintLoading}><BugPlay size={16} />
                      {isLoading ? <span className="loading loading-spinner loading-sm"></span> : 'Debug my code'}
                    </button>
                  </div>
                </section>

                <section className="flex h-[540px] min-h-0 flex-col sm:h-[620px] xl:h-auto">
                  <div className="card bg-base-200 shadow-sm flex-1 flex flex-col min-h-0 overflow-hidden border border-base-300">

                    <div className="bg-base-300 px-4 py-3 rounded-t-box border-b border-base-300/50 flex items-center">
                      <Sparkles className="mr-3 text-primary size-6" />
                      <h2 className="font-semibold text-xl tracking-wider">LLM ASSISTANT</h2>
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
                          <div className="alert alert-success text-sm p-3 flex-col items-start gap-1.5">
                            <CheckCircle2 size={16} className="shrink-0 my-auto" />
                            <span className="font-bold my-auto">Execution Successful</span>
                            {result.stdout && <pre className="max-h-48 w-full overflow-auto rounded bg-black/10 p-2 text-sm">{result.stdout}</pre>}
                          </div>
                        )}

                        {result?.error && (
                          <div className="alert alert-error text-sm p-3 flex-col items-start gap-1">
                            <div className="w-full flex font-bold gap-2">
                              <AlertCircle size={16} className="shrink-0 my-auto" />
                              <span>{result.error.error_type}</span>
                              {result.error.line_number && <span>Line {result.error.line_number}</span>}
                            </div>
                            <p>{result.error.message}</p>
                          </div>
                        )}
                      </div>

                      <div className="flex-1 bg-base-100 rounded-box border border-base-300 flex flex-col overflow-hidden">

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
                                  {m.text}
                                </div>
                                {showResource && (
                                  <a
                                    href={m.resourceUrl!}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="chat-footer mt-2 btn btn-sm btn-outline btn-primary gap-2"
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

                          {result?.error && currentStage === null && !isHintLoading && !isLoading && (
                            <button className="btn btn-outline btn-primary pointer-events-auto self-start" onClick={handleGetHint}>
                              <HandHelping size={16} />
                              Get a hint
                            </button>
                          )}

                          {isHintLoading && <p className="text-sm opacity-70">Thinking...</p>}
                          {hintError && <p className="text-sm text-error">{hintError}</p>}

                          {isFinalStage && (
                            <p className="text-xs opacity-60 text-center py-2">
                              That is the last hint for this error. Fix your code and run it again.
                            </p>
                          )}

                        </div>

                        <div className="flex gap-2 bg-base-300 p-2">
                          <input
                            type="text"
                            className="input input-md flex-1 bg-base-100 font-medium focus:outline-none focus:border-primary"
                            placeholder={
                              isFinalStage
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
                            disabled={currentStage === null || isLoading || isHintLoading || isFinalStage}
                          />
                          <button
                            className="btn btn-outline btn-primary pointer-events-auto"
                            onClick={handleSend}
                            disabled={
                              currentStage === null || isLoading || isHintLoading || !input.trim() || isFinalStage
                            }
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
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="/register" element={<Navigate to="/" replace />} />
      <Route path="/student/setup" element={<StudentSetupPage />} />
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
