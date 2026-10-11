/**
 * Intro tour for the Student View. Points out the main parts of the page
 * one at a time, using the data-tour markers in App.tsx. With an empty
 * editor it runs as a demo: it puts in sample code and the student runs it.
 */
import { driver, type Driver, type DriveStep } from 'driver.js';
import 'driver.js/dist/driver.css';
import type { ExecutionResponse } from '../types';

type TourOptions = {
  languageLabel: string;    // e.g. "Python"
  extension: string;        // e.g. "py"
  demo: boolean;            // true when the editor was empty, so sample code can be used
  onLoadSample: () => void; // puts the sample code in the editor
  onEnd: () => void;        // tidies up after the tour, however it ends
};

// Broken sample code the tour puts in the editor, with the result Run shows
// for it. The result is made up on the frontend so tour runs never reach the
// backend or the instructor stats. error_id is null, so no hint is fetched.
type TourSample = { code: string; result: ExecutionResponse };

const tourSamples: Record<string, TourSample> = {
  Python: {
    code: 'numbers = [1, 2, 3]\nprint(numbers[3])\n',
    result: {
      stdout: '',
      stderr: 'IndexError: list index out of range',
      exit_code: 1,
      status: null,
      timed_out: false,
      error: {
        error_type: 'IndexError',
        message: 'list index out of range',
        line_number: 2,
        code_snippet: 'print(numbers[3])',
      },
      error_id: null,
    },
  },
  Java: {
    code:
      'public class Main {\n' +
      '    public static void main(String[] args) {\n' +
      '        int[] numbers = {1, 2, 3};\n' +
      '        System.out.println(numbers[3]);\n' +
      '    }\n' +
      '}\n',
    result: {
      stdout: '',
      stderr: 'ArrayIndexOutOfBoundsException: Index 3 out of bounds for length 3',
      exit_code: 1,
      status: null,
      timed_out: false,
      error: {
        error_type: 'ArrayIndexOutOfBoundsException',
        message: 'Index 3 out of bounds for length 3',
        line_number: 4,
        code_snippet: 'System.out.println(numbers[3]);',
      },
      error_id: null,
    },
  },
  JavaScript: {
    code: 'const numbers = [1, 2, 3];\nconsole.log(numbers[3].toFixed(1));\n',
    result: {
      stdout: '',
      stderr: "TypeError: Cannot read properties of undefined (reading 'toFixed')",
      exit_code: 1,
      status: null,
      timed_out: false,
      error: {
        error_type: 'TypeError',
        message: "Cannot read properties of undefined (reading 'toFixed')",
        line_number: 2,
        code_snippet: 'console.log(numbers[3].toFixed(1));',
      },
      error_id: null,
    },
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
  typeof step.element === 'string' && isOnScreen(step.element) ? [step] : [];

const buildSteps = (options: TourOptions, tour: Driver): DriveStep[] => {
  const { languageLabel, extension, demo, onLoadSample } = options;

  const welcome: DriveStep = {
    popover: {
      title: 'Welcome!',
      description: demo
        ? "Here's a quick look around. You'll try running some broken code to see how it works. You can close this any time."
        : "Here's a quick look around before you start. You can close this any time.",
    },
  };

  const editor: DriveStep = {
    element: '[data-tour="editor"]',
    popover: {
      title: 'Your code',
      description: `Type or paste the ${languageLabel} code that isn't working here.`,
      side: 'right',
    },
  };

  const divider = ifOnScreen({
    element: '[data-tour="divider"]',
    popover: {
      title: 'Make more room',
      description: 'Drag this line to give your code or the assistant more space. Double-click it to reset.',
    },
  });

  const replyBox: DriveStep = {
    element: '[data-tour="chat-input"]',
    popover: {
      title: 'Reply to the assistant',
      description: 'With hints, answer the assistant here to unlock the next hint.',
      side: 'top',
    },
  };

  const help: DriveStep = {
    element: '[data-tour="help"]',
    popover: {
      title: 'Need this again?',
      description: 'Click here any time to replay this tour.',
      side: 'bottom',
      align: 'end',
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
          title: 'Run your code',
          description: 'Click Run to run your code safely. Run it again whenever you make a change.',
          side: 'bottom',
        },
      },
      {
        element: '[data-tour="output"]',
        popover: {
          title: 'See what happened',
          description: 'Anything your program prints shows up here. If it crashes, the error appears in red.',
          side: 'top',
        },
      },
      {
        element: '[data-tour="assistant"]',
        popover: {
          title: 'Get help with errors',
          description:
            'When your code has an error, the assistant tells you what happened and which line to look at. You can then pick a hint to work it out step by step, or ask for the answer.',
          side: 'left',
        },
      },
      replyBox,
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
        title: 'Or upload a file',
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
        title: 'Run your code',
        description: "We've put some broken code in for you. Click Run to see what happens.",
        side: 'bottom',
        showButtons: ['close'], // App moves the tour on once the result shows
      },
    },
    {
      element: '[data-tour="output"]',
      popover: {
        title: 'See what happened',
        description: 'Your program crashed, so the error shows here in red. Anything your program prints shows up here too.',
        side: 'top',
      },
    },
    {
      element: '[data-tour="error"]',
      popover: {
        title: 'What happened and where',
        description: 'This explains the error in plain words. "Go to line" jumps straight to the line to look at.',
        side: 'left',
      },
    },
    {
      element: '[data-tour="help-choice"]',
      popover: {
        title: 'Choose how you want help',
        description:
          'A hint walks you through finding the fix yourself, one step at a time. Show me the answer explains the error and the fix straight away.',
        side: 'left',
      },
    },
    replyBox,
    ...divider,
    help,
  ];
};

// Whether this browser has finished or skipped the tour, so it only starts
// by itself the first time. Stored in the browser until student login
// exists; then this can move to the student's account.
const tourStatusKey = 'debugging-assistant.tour-status';
type TourStatus = 'completed' | 'skipped';

export const hasSeenTour = (): boolean => {
  try {
    const status = localStorage.getItem(tourStatusKey);
    return status === 'completed' || status === 'skipped';
  } catch {
    return true; // storage blocked: don't start it every time
  }
};

const saveTourStatus = (status: TourStatus) => {
  try {
    localStorage.setItem(tourStatusKey, status);
  } catch {
    // Storage blocked, the tour may start again next time.
  }
};

// Starts the tour from the first step. Returns it so App can move it on
// once the student has clicked Run.
export const startStudentTour = (options: TourOptions): Driver => {
  const tour = driver({
    disableActiveInteraction: true,
    showProgress: true,
    progressText: '{{current}} of {{total}}',
    nextBtnText: 'Next',
    prevBtnText: 'Back',
    doneBtnText: 'Done',
    popoverClass: 'student-tour',
    // Runs however the tour closes: Done, the X, Escape or clicking outside.
    // Done on the last step counts as completed, anything else as skipped.
    onDestroyStarted: () => {
      saveTourStatus(tour.hasNextStep() ? 'skipped' : 'completed');
      options.onEnd();
      tour.destroy();
    },
  });
  tour.setSteps(buildSteps(options, tour));
  tour.drive();
  return tour;
};
