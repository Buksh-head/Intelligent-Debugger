// Explanation panel under the socratic answer (#68): how the system reached
// its diagnosis. Collapsed by default, and renders whatever subset of the
// explanation arrived, or nothing.

import { useState } from 'react';
import type { Explanation } from '../types';

// Show only the top few reasons so the panel stays short.
const MAX_ATTRIBUTIONS = 3;

// Turns labels like "off-by-one" into "off by one" for display.
const readable = (misconception: string) => misconception.replace(/-/g, ' ');

function WhyThisHint({ explanation }: { explanation?: Explanation | null }) {
  const [open, setOpen] = useState(false);

  if (!explanation) return null;

  const reasoning = explanation.reasoning?.trim();
  const misconception = explanation.misconception?.trim();
  const attributions = (explanation.attributions ?? []).slice(0, MAX_ATTRIBUTIONS);

  if (!reasoning && !misconception && attributions.length === 0) return null;

  return (
    <div className="chat-footer mt-2 w-full max-w-full flex-col items-start gap-0 rounded-box border border-base-300 bg-base-200 px-3 py-2 text-sm">
      <button
        type="button"
        className="btn btn-ghost btn-xs gap-1 px-0"
        aria-expanded={open}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <span aria-hidden="true">{open ? '▾' : '▸'}</span>
        How did it work this out?
      </button>

      {open && (
        <div className="mt-2 space-y-3">
          {reasoning && <p className="whitespace-pre-wrap text-base-content/80">{reasoning}</p>}

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
              <p className="mb-1 text-base-content/60">What pointed there (strongest first):</p>
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

export default WhyThisHint;
