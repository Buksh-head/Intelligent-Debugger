/**
 * Stage 2 hints: the student replies to the hint question in their own words,
 * and gets back either a new leading question (they can reply again) or a
 * short answer that ends the hints for this run.
 *
 * Rendered under the stage 1 hint with `key` set to that hint, so a new run or
 * a new hint starts a fresh conversation. A conversation restored from a saved
 * session starts from `initialSteps`; each new step is passed to `onStep` so
 * the Student View can save it.
 */

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, KeyRound, Lightbulb, Send } from "lucide-react";
import { createPortal } from "react-dom";
import { getFollowUpHint } from "../api";
import type {
  ExecutionResponse,
  FollowUpHint,
  HintTurn,
  SavedErrorRef,
} from "../types";
import type { HintStep } from "../session/savedSession";

const MAX_REPLY_CHARS = 1000;

type Props = {
  code: string;
  stdin: string;
  execution: ExecutionResponse;
  firstQuestion: string;
  // The output the student expected, when the hints are about a logic error.
  expected?: string;
  // The saved session and error, so each follow-up is recorded for the dashboard.
  saved?: SavedErrorRef;
  initialSteps?: HintStep[];
  composerHost: HTMLDivElement | null;
  onStep?: (step: HintStep) => void;
  onShowAnswer?: () => void;
  onLookAtLine: (line: number) => void;
  errorMessage: (err: unknown, fallback: string) => string;
};

export default function FollowUpHints({
  code,
  stdin,
  execution,
  firstQuestion,
  expected,
  saved,
  initialSteps,
  composerHost,
  onStep,
  onShowAnswer,
  onLookAtLine,
  errorMessage,
}: Props) {
  const [steps, setSteps] = useState<HintStep[]>(initialSteps ?? []);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  // A response that arrives after this component is gone (new run) is dropped.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const last = steps[steps.length - 1]?.response;
  const done = last?.final ?? false;
  const currentQuestion = last ? last.text : firstQuestion;

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [steps.length, error]);

  const showAnswerButton = onShowAnswer && (
    <button
      type="button"
      className="btn btn-sm btn-ghost min-w-0 justify-start px-2 text-left"
      onClick={onShowAnswer}
    >
      <KeyRound size={14} />
      Still stuck? Show me the answer
    </button>
  );

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    const reply = draft.trim();
    if (!reply || isLoading || done) return;
    // Every question so far, each with the reply the student gave to it.
    const asked = [firstQuestion, ...steps.map((s) => s.response.text)];
    const replies = [...steps.map((s) => s.reply), reply];
    const turns: HintTurn[] = asked.map((question, i) => ({
      question,
      reply: replies[i],
    }));
    setIsLoading(true);
    setError(null);
    try {
      const response = await getFollowUpHint(
        code,
        stdin,
        execution,
        turns,
        expected,
        saved,
      );
      if (!mounted.current) return;
      setSteps((prev) => [...prev, { reply, response }]);
      onStep?.({ reply, response });
      setDraft("");
    } catch (err) {
      if (!mounted.current) return;
      setError(errorMessage(err, "Failed to get the next hint."));
    } finally {
      if (mounted.current) setIsLoading(false);
    }
  };

  const composer = (
    <>
      {!done && (
        <form
          onSubmit={send}
          className="flex flex-col gap-2 rounded-b-box border-t border-base-300 bg-base-100 px-3 pt-3 pb-3 sm:px-4"
        >
          <div className="flex flex-col items-stretch gap-2">
            <textarea
              id="hint-reply"
              className="textarea textarea-bordered h-[3.75rem] min-h-[3.75rem] max-h-[3.75rem] w-full resize-none overflow-y-auto rounded-lg text-sm"
              rows={2}
              maxLength={MAX_REPLY_CHARS}
              placeholder="Answer the question in your own words and you'll get the next hint..."
              aria-label={`Your answer to: ${currentQuestion}`}
              value={draft}
              disabled={isLoading}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // Enter sends, Shift+Enter adds a new line.
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              {showAnswerButton}
              <button
                type="submit"
                className="btn btn-sm btn-primary ml-auto"
                disabled={!draft.trim() || isLoading}
              >
                {isLoading ? (
                  <span className="loading loading-dots loading-sm"></span>
                ) : (
                  <Send size={14} />
                )}
                Send answer
              </button>
            </div>
          </div>
        </form>
      )}
      {done && showAnswerButton && (
        <div className="rounded-b-box border-t border-base-300 bg-base-100 px-3 pt-3 pb-3 sm:px-4">
          <div className="flex justify-end">{showAnswerButton}</div>
        </div>
      )}
    </>
  );

  return (
    <>
      <div className="flex flex-col gap-3" data-tour="follow-up">
        {steps.map((step, i) => (
          <article key={i} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-box border border-base-300 bg-base-200 px-4 py-3 text-sm shadow-sm">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-base-content/50">
                  Your reply
                </p>
                <p className="whitespace-pre-wrap">{step.reply}</p>
              </div>
            </div>
            <ResponseCard
              response={step.response}
              number={i + 2}
              onLookAtLine={onLookAtLine}
            />
          </article>
        ))}
        <div ref={conversationEndRef} aria-hidden="true" />

        {error && <p className="text-sm text-error">{error}</p>}
      </div>
      {composerHost && createPortal(composer, composerHost)}
    </>
  );
}

function ResponseCard({
  response,
  number,
  onLookAtLine,
}: {
  response: FollowUpHint;
  number: number;
  onLookAtLine: (line: number) => void;
}) {
  const isAnswer = response.kind === "answer";
  return (
    <div
      className={
        isAnswer
          ? "rounded-box border border-success/40 bg-success/10 p-4"
          : "rounded-box border border-primary/40 bg-primary/10 p-4"
      }
    >
      <p
        className={`mb-2 flex items-center gap-2 text-xs font-semibold tracking-wide ${
          isAnswer ? "text-success" : "text-primary"
        }`}
      >
        {isAnswer ? <CheckCircle2 size={16} /> : <Lightbulb size={16} />}
        {isAnswer
          ? `HINT ${number}: WHAT'S GOING ON`
          : `HINT ${number}: A QUESTION TO THINK ABOUT`}
      </p>
      <p className="text-base leading-relaxed sm:text-lg">{response.text}</p>
      {response.cause_line && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-sm btn-outline btn-primary"
            onClick={() => onLookAtLine(response.cause_line!)}
          >
            Look at line {response.cause_line}
          </button>
          {isAnswer && (
            <p className="text-xs text-base-content/60">
              Make your change, then run the code again.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
