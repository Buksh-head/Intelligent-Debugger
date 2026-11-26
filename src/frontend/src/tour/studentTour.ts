/**
 * Intro tour for the Student View. Points out the main parts of the page
 * one at a time, using the data-tour markers in App.tsx. With an empty
 * editor it runs as a demo: it puts in sample code and the student runs it.
 */
import { driver, type Driver, type DriveStep } from "driver.js";
import "driver.js/dist/driver.css";
import type { ExecutionResponse, Stage1Hint } from "../types";
import { saveTourStatus } from "./tourStatus";

type TourOptions = {
  languageLabel: string; // e.g. "Python"
  extension: string; // e.g. "py"
  demo: boolean; // true when the editor was empty, so sample code can be used
  onLoadSample: () => void; // puts the sample code in the editor
  onEnd: () => void; // tidies up after the tour, however it ends
};

// Broken sample code the tour puts in the editor, with the result Run shows
// for it and the hint "Give me a hint" shows. Both are made up on the
// frontend so tour runs never reach the backend.
type TourSample = { code: string; result: ExecutionResponse; hint: Stage1Hint };

const sampleHint = (question: string, line: number): Stage1Hint => ({
  question,
  error_type: null,
  error_line: line,
  cause_line: line,
  source: "fallback",
});

const tourSamples: Record<string, TourSample> = {
  Python: {
    code: "numbers = [1, 2, 3]\nprint(numbers[3])\n",
    result: {
      stdout: "",
      stderr: "IndexError: list index out of range",
      exit_code: 1,
      status: null,
      timed_out: false,
      error: {
        error_type: "IndexError",
        message: "list index out of range",
        line_number: 2,
        code_snippet: "print(numbers[3])",
        friendly_title: "That position doesn't exist in the list",
        friendly_message:
          "On line 2, you ask for an item by its position with [ ], but the list doesn't have an item at that position.",
      },
      error_id: null,
    },
    hint: sampleHint(
      "On line 2 you ask for numbers[3]. How many items are in numbers, and what position number does Python give the first one?",
      2,
    ),
  },
  Java: {
    code:
      "public class Main {\n" +
      "    public static void main(String[] args) {\n" +
      "        int[] numbers = {1, 2, 3};\n" +
      "        System.out.println(numbers[3]);\n" +
      "    }\n" +
      "}\n",
    result: {
      stdout: "",
      stderr:
        "ArrayIndexOutOfBoundsException: Index 3 out of bounds for length 3",
      exit_code: 1,
      status: null,
      timed_out: false,
      error: {
        error_type: "ArrayIndexOutOfBoundsException",
        message: "Index 3 out of bounds for length 3",
        line_number: 4,
        code_snippet: "System.out.println(numbers[3]);",
        friendly_title: "That position doesn't exist in the array",
        friendly_message:
          "On line 4, you ask for an item by its position with [ ], but the array doesn't have an item at that position.",
      },
      error_id: null,
    },
    hint: sampleHint(
      "On line 4 you ask for numbers[3]. How many items are in numbers, and what index does Java give the first one?",
      4,
    ),
  },
  JavaScript: {
    code: "const numbers = [1, 2, 3];\nconsole.log(numbers[3].toFixed(1));\n",
    result: {
      stdout: "",
      stderr:
        "TypeError: Cannot read properties of undefined (reading 'toFixed')",
      exit_code: 1,
      status: null,
      timed_out: false,
      error: {
        error_type: "TypeError",
        message: "Cannot read properties of undefined (reading 'toFixed')",
        line_number: 2,
        code_snippet: "console.log(numbers[3].toFixed(1));",
        friendly_title: "The value is undefined, so it has no .toFixed",
        friendly_message:
          "On line 2, you use .toFixed on a value, but that value is undefined, which means \"no value\".",
      },
      error_id: null,
    },
    hint: sampleHint(
      "On line 2 you ask for numbers[3]. How many items are in numbers, and what index does JavaScript give the first one?",
      2,
    ),
  },
};

// The sample for the student's language, falling back to Python.
export const getTourSample = (languageLabel: string): TourSample =>
  tourSamples[languageLabel] ?? tourSamples.Python;

// Marker for the Run step, so App can tell when the tour is waiting on Run.
export const tourRunStep = '[data-tour="run"]';

// Whether an element is on screen right now. The upload button goes once
// there is code in the editor, and the divider is hidden on smaller screens.
const isOnScreen = (selector: string): boolean => {
  const element = document.querySelector(selector);
  return element !== null && element.getClientRects().length > 0;
};

// Includes a step only if its element is on screen when the tour starts.
const ifOnScreen = (step: DriveStep): DriveStep[] =>
  typeof step.element === "string" && isOnScreen(step.element) ? [step] : [];

const buildSteps = (options: TourOptions, tour: Driver): DriveStep[] => {
  const { languageLabel, extension, demo, onLoadSample } = options;

  const welcome: DriveStep = {
    popover: {
      title: "Welcome!",
      description: demo
        ? "Here's a quick look around. You'll try running some broken code to see how it works. You can close this any time."
        : "Here's a quick look around before you start. You can close this any time.",
    },
  };

  const editor: DriveStep = {
    element: '[data-tour="editor"]',
    popover: {
      title: "Your code",
      description: `Type or paste the ${languageLabel} code that isn't working here.`,
      side: "right",
    },
  };

  const divider = ifOnScreen({
    element: '[data-tour="divider"]',
    popover: {
      title: "Make more room",
      description:
        "Drag this line to give your code or the hints more space. Double-click it to reset.",
    },
  });

  const help: DriveStep = {
    element: '[data-tour="help"]',
    popover: {
      title: "Need this again?",
      description: "Click here any time to replay this tour.",
      side: "bottom",
      align: "end",
    },
  };

  // Student already has code: describe each part without running anything.
  if (!demo) {
    return [
      welcome,
      editor,
      {
        element: tourRunStep,
        popover: {
          title: "Run your code",
          description:
            "Click Run to run your code safely. Run it again whenever you make a change.",
          side: "bottom",
        },
      },
      {
        element: '[data-tour="output"]',
        popover: {
          title: "See what happened",
          description:
            "Anything your program prints shows up here. If it crashes, the error appears in red.",
          side: "top",
        },
      },
      {
        element: '[data-tour="assistant"]',
        popover: {
          title: "Get help with errors",
          description:
            "When your code has an error, this tells you what happened and which line to look at. You can then ask for a hint: a question that points you towards the problem so you can fix it yourself.",
          side: "left",
        },
      },
      ...divider,
      help,
    ];
  }

  // Demo: put in sample code after the upload step, then have the student run it.
  return [
    welcome,
    editor,
    {
      element: '[data-tour="upload"]',
      popover: {
        title: "Or upload a file",
        description: `Already have your code in a .${extension} file? Upload it here instead. Click Next and we'll put in some broken code for you to try.`,
        onNextClick: () => {
          onLoadSample();
          tour.moveNext();
        },
      },
    },
    {
      element: tourRunStep,
      disableActiveInteraction: false, // the student clicks Run here
      popover: {
        title: "Run your code",
        description:
          "We've put some broken code in for you. Click Run to see what happens.",
        side: "bottom",
        showButtons: ["close"], // App moves the tour on once the result shows
      },
    },
    {
      element: '[data-tour="output"]',
      popover: {
        title: "See what happened",
        description:
          "Your program crashed, so the error shows here in red. Anything your program prints shows up here too.",
        side: "top",
      },
    },
    {
      element: '[data-tour="error"]',
      popover: {
        title: "What happened and where",
        description:
          'This explains the error in plain words, without the jargon. "Go to line" jumps straight to the line Python stopped at.',
        side: "left",
      },
    },
    {
      element: '[data-tour="help-choice"]',
      popover: {
        title: "Ask for a hint",
        description:
          "A hint is a question about your code. It points you at what to check, without giving the answer away, so you find the fix yourself.",
        side: "left",
      },
    },
    ...divider,
    help,
  ];
};

// Starts the tour from the first step. Returns it so App can move it on
// once the student has clicked Run.
export const startStudentTour = (options: TourOptions): Driver => {
  const tour = driver({
    // Highlighted elements can't be clicked during the tour. The demo's
    // Run step turns this back off so the student can click Run.
    disableActiveInteraction: true,
    showProgress: true,
    progressText: "{{current}} of {{total}}",
    nextBtnText: "Next",
    prevBtnText: "Back",
    doneBtnText: "Done",
    popoverClass: "student-tour",
    // Runs however the tour closes: Done, the X, Escape or clicking outside.
    // Done on the last step counts as completed, anything else as skipped.
    // Saved to the student's account so it only starts by itself once.
    onDestroyStarted: () => {
      void saveTourStatus(
        "student",
        tour.hasNextStep() ? "skipped" : "completed",
      );
      options.onEnd();
      tour.destroy();
    },
  });
  tour.setSteps(buildSteps(options, tour));
  tour.drive();
  return tour;
};
