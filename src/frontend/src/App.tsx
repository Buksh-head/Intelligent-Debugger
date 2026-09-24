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
import { executeCode, getHint } from './api';
import type { ExecutionResponse, Finding, HintStage } from './types';

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
  Palette,
  ChevronDown,
  Bot,
  UserRound,
  BookOpen,
  ExternalLink,
} from 'lucide-react';

type MonacoEditor = Parameters<OnMount>[0];
type DecorationsCollection = ReturnType<MonacoEditor['createDecorationsCollection']>;

type ChatMessage = {
  role: 'student' | 'assistant';
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

  const navigate = useNavigate();
  const { signOut } = useAuth();

  const storedStudentContext = sessionStorage.getItem('debugging-assistant.student-context');
  const selectedCourse = (() => {
    try {
      return storedStudentContext
        ? (JSON.parse(storedStudentContext) as { course?: string }).course ?? ''
        : '';
    } catch {
      return '';
    }
  })();
  const editorLanguage = courseEditorLanguages[selectedCourse] ?? courseEditorLanguages.CSSE1001;

  const editorRef = useRef<MonacoEditor | null>(null);
  const decorationsRef = useRef<DecorationsCollection | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);

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

  // A fresh run or edit means the existing conversation no longer applies.
  const resetConversation = () => {
    setMessages([]);
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

      setResult(null);
      setApiError(null);
      resetConversation();
    };
    reader.readAsText(file);

    event.target.value = '';
  };

  const handleDebug = async () => {
    if (!code.trim()) {
      setApiError('Please write some code before debugging.');
      setResult(null);
      resetConversation();
      return;
    }
    setIsLoading(true);
    setApiError(null);
    resetConversation();
    try {
      const storedContext = sessionStorage.getItem('debugging-assistant.student-context');
      const studentContext = storedContext ? JSON.parse(storedContext) as { course?: string; language?: string } : {};
      const response = await executeCode(code, expectedBehavior, studentContext.course, studentContext.language ?? editorLanguage.label);
      setResult(response);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Failed to reach the backend.');
      setResult(null);
    } finally {
      setIsLoading(false);
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
    setIsHintLoading(true);
    setHintError(null);
    try {
      const response = await getHint(result.error_id, buildFinding(result), result);
      const first = response.hints[0];
      if (first?.text) {
        setMessages([toAssistantMessage(first)]);
        setCurrentStage(first.stage);
      } else {
        setHintError('No hint came back. Try again in a moment.');
      }
    } catch (err) {
      setHintError(err instanceof Error ? err.message : 'Failed to get a hint.');
      setMessages([]);
    } finally {
      setIsHintLoading(false);
    }
  };

  // Sends the student's reply. The backend classifies it against the current
  // stage task and decides whether the stage advances - the stage itself is
  // never sent from here.
  const handleSend = async () => {
    if (!input.trim() || isHintLoading || isFinalStage) return;
    if (!result?.error || result.error_id == null) return;

    const studentText = input.trim();
    const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant');

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
      setHintError(err instanceof Error ? err.message : 'Failed to reach the assistant.');
    } finally {
      setIsHintLoading(false);
    }
  };

  return (
    <Routes>
      <Route
        path="/student"
        element={
          <>
            <div className="min-h-screen p-3 sm:p-5">
              <header className="navbar mb-4 flex-col items-stretch gap-4 lg:flex-row lg:items-center">
                <div className="flex flex-1 items-center gap-3">
                  <img
                    src={editorLanguage.logo}
                    alt={`${editorLanguage.label} logo`}
                    className="h-10 shrink-0 sm:h-[50px]"
                  />
                  <div className="min-w-0">
                    <h1 className="font-mono text-xl font-semibold leading-tight tracking-wide text-primary sm:text-2xl sm:tracking-wider lg:text-3xl">INTELLIGENT {editorLanguage.label.toUpperCase()} DEBUGGER</h1>
                    <p className='mt-1'>Student View{selectedCourse ? ` | ${selectedCourse}` : ''}</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:gap-4 lg:flex-nowrap">
                  <div className="dropdown dropdown-end">
                    <button type="button" tabIndex={0} className="btn btn-outline btn-primary">
                      <Palette size={16} />
                      Theme: {themeOptions.find((option) => option.value === theme)?.label}
                      <ChevronDown size={16} />
                    </button>
                    <ul tabIndex={0} className="dropdown-content menu z-20 mt-2 w-48 rounded-box bg-base-100 p-2 shadow-lg">
                      {themeOptions.map((themeOption) => (
                        <li key={themeOption.value}>
                          <button
                            type="button"
                            className={theme === themeOption.value ? 'active' : ''}
                            aria-current={theme === themeOption.value ? 'true' : undefined}
                            onClick={() => setTheme(themeOption.value)}
                          >
                            {themeOption.label}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <button
                    type="button"
                    className="btn btn-outline btn-primary"
                    onClick={async () => {
                      await signOut();
                      navigate('/');
                    }}
                  >
                    <LogOut size={16} />
                    Log out
                  </button>
                </div>
              </header>

              <main className="grid min-h-0 grid-cols-1 gap-4 xl:grid-cols-2 xl:gap-6">
                <section className="flex flex-col gap-3 xl:h-[660px]">
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
                        theme="vs-dark"
                        value={code}
                        onChange={(value) => {
                          setCode(value || '');
                          setResult(null);
                          setApiError(null);
                          resetConversation();
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
                    <button className="btn btn-outline btn-primary pointer-events-auto mt-2 h-11 w-full" onClick={handleDebug} disabled={isLoading}><BugPlay size={16} />
                      {isLoading ? <span className="loading loading-spinner loading-sm"></span> : 'Debug my code'}
                    </button>
                  </div>
                </section>

                <section className="flex h-[540px] min-h-0 flex-col sm:h-[620px] xl:h-[660px]">
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
                          {!result?.error && !isLoading && (
                            <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-base opacity-50 sm:flex-row sm:text-lg">
                              <span>Submit code to see feedback here</span>
                              <SquareCode className='size-8 sm:size-9' />
                            </div>
                          )}

                          {result?.error && messages.length === 0 && !isHintLoading && (
                            <button className="btn btn-outline btn-primary pointer-events-auto self-start" onClick={handleGetHint}>
                              <HandHelping size={16} />
                              Get a hint
                            </button>
                          )}

                          {messages.map((m, i) => {
                            // Show the resource link only on the message that first offered it,
                            // not on every follow-up while the gate is open.
                            const showResource =
                              m.resourceUrl &&
                              !messages.slice(0, i).some((p) => p.resourceUrl === m.resourceUrl);

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
                            disabled={messages.length === 0 || isHintLoading || isFinalStage}
                          />
                          <button
                            className="btn btn-outline btn-primary pointer-events-auto"
                            onClick={handleSend}
                            disabled={
                              messages.length === 0 || isHintLoading || !input.trim() || isFinalStage
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
            <InstructorDashboard
              onBack={async () => {
                await signOut();
                navigate('/');
              }}
            />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
