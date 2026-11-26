// Socratic mode: the whole answer, what went wrong and how to fix it, with a
// collapsed "How did it work this out?" panel underneath. The panel is the
// team version's WhyThisHint: the model's reasoning, the misconception the
// classifier picked and what in the code pointed there (SHAP).

import { useState } from "react";
import { KeyRound } from "lucide-react";
import type { Explanation, SocraticAnswer } from "../types";

// Show only the top few reasons so the panel stays short.
const MAX_ATTRIBUTIONS = 3;

// Turns labels like "off-by-one" into "off by one" for display.
const readable = (misconception: string) => misconception.replace(/-/g, " ");

export function HowItWorkedThisOut({
  explanation,
}: {
  explanation?: Explanation | null;
}) {
  const [open, setOpen] = useState(false);

  if (!explanation) return null;

  const reasoning = explanation.reasoning?.trim();
  const misconception = explanation.misconception?.trim();
  const attributions = (explanation.attributions ?? []).slice(
    0,
    MAX_ATTRIBUTIONS,
  );

  if (!reasoning && !misconception && attributions.length === 0) return null;

  return (
    <div className="mt-3 rounded-box border border-base-300 bg-base-200 px-3 py-2 text-sm">
      <button
        type="button"
        className="btn btn-ghost btn-xs gap-1 px-0"
        aria-expanded={open}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        How did it work this out?
      </button>

      {open && (
        <div className="mt-2 space-y-3">
          {reasoning && (
            <p className="whitespace-pre-wrap text-base-content/80">
              {reasoning}
            </p>
          )}

          {/* No confidence figure: the classifier's probability is an uncalibrated
              softmax output, so a percentage would overstate what it knows. */}
          {misconception && (
            <p>
              <span className="text-base-content/60">This looks like: </span>
              <span className="font-medium">{readable(misconception)}</span>
            </p>
          )}

          {attributions.length > 0 && (
            <div>
              <p className="mb-1 text-base-content/60">
                What pointed there (strongest first):
              </p>
              <ul className="list-inside list-disc space-y-1">
                {attributions.map((attribution) => (
                  <li key={attribution.feature}>{attribution.label}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SocraticAnswerCard({
  answer,
  onLookAtLine,
}: {
  answer: SocraticAnswer;
  onLookAtLine: (line: number) => void;
}) {
  return (
    <div
      data-testid="socratic-answer"
      className="rounded-box border border-secondary/40 bg-secondary/10 p-4"
    >
      <p className="mb-3 flex items-center gap-2 text-xs font-semibold tracking-wide text-secondary">
        <KeyRound size={16} />
        THE ANSWER
      </p>
      <div className="space-y-3">
        {answer.diagnosis && (
          <div>
            <p className="mb-1 font-semibold">What went wrong</p>
            <p className="whitespace-pre-wrap leading-relaxed">
              {answer.diagnosis}
            </p>
          </div>
        )}
        {answer.fix && (
          <div>
            <p className="mb-1 font-semibold">How to fix it</p>
            <p className="whitespace-pre-wrap leading-relaxed">{answer.fix}</p>
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {answer.error_line && (
          <button
            type="button"
            className="btn btn-sm btn-outline btn-secondary"
            onClick={() => onLookAtLine(answer.error_line!)}
          >
            Look at line {answer.error_line}
          </button>
        )}
        <p className="text-xs text-base-content/60">
          Make the change, then run your code again to check it works.
        </p>
      </div>
      <HowItWorkedThisOut explanation={answer.explanation} />
    </div>
  );
}

export default SocraticAnswerCard;
