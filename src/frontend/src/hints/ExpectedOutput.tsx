/**
 * The Expected behaviour tab of the Output panel. Shown once a run finishes
 * without an error: the student types what they expected the program to
 * print and checks the real output against it. The result, and a hint when
 * they differ, appear in the Hints panel.
 */

import { ListChecks } from "lucide-react";

const MAX_EXPECTED_CHARS = 5000;

type Props = {
  value: string;
  onChange: (value: string) => void;
  onCheck: () => void;
  isChecking: boolean;
  theme: string;
};

export default function ExpectedOutput({
  value,
  onChange,
  onCheck,
  isChecking,
  theme,
}: Props) {
  return (
    <form
      className={`student-output-surface flex flex-1 flex-col gap-2 overflow-auto rounded-b-box border border-base-300 px-4 py-3 text-sm ${theme === "light" ? "bg-white" : "bg-[#1e1e1e]"}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim() && !isChecking) onCheck();
      }}
    >
      <label htmlFor="expected-output" className="text-base-content/70">
        Your program ran without errors. What did you expect it to print? Type
        it exactly, one line for each line of output.
      </label>
      <textarea
        id="expected-output"
        aria-label="Expected output"
        className="textarea textarea-sm w-full flex-1 font-mono"
        rows={4}
        maxLength={MAX_EXPECTED_CHARS}
        placeholder={"For example:\n15"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="submit"
        className="btn btn-sm btn-primary self-end"
        disabled={!value.trim() || isChecking}
      >
        {isChecking ? (
          <span className="loading loading-dots loading-sm"></span>
        ) : (
          <ListChecks size={14} />
        )}
        Check my output
      </button>
    </form>
  );
}
