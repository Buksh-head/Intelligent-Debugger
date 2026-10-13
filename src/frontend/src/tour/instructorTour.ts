/**
 * Intro tour for the instructor dashboard. Has one set of steps for the
 * overview and one for an error type's detail view, picked by whichever is
 * on screen. Uses the data-tour markers in InstructorDashboard.tsx.
 */
import { driver, type Driver, type DriveStep } from 'driver.js';
import 'driver.js/dist/driver.css';
import { saveTourStatus } from './tourStatus';

export type InstructorTourView = 'overview' | 'detail';

const help: DriveStep = {
    element: '[data-tour="help"]',
    popover: {
        title: 'Need this again?',
        description: 'Click here any time to replay this tour. Open an error type first to get a tour of its details page.',
        side: 'bottom',
        align: 'end',
    },
};

const overviewSteps: DriveStep[] = [
    {
        popover: {
            title: 'Welcome to the instructor dashboard',
            description:
                "Here's a quick look at how to read your class's errors. Every number here is anonymous and grouped across students. You can close this any time.",
        },
    },
    {
        element: '[data-tour="filters"]',
        popover: {
            title: 'Choose a class and dates',
            description: 'Pick a class and a date range. Everything on the page updates to match.',
            side: 'bottom',
            align: 'end',
        },
    },
    {
        element: '[data-tour="stats"]',
        popover: {
            title: 'The big picture',
            description:
                'How many debugging sessions were looked at, how many errors were found, and the concept students struggled with most.',
            side: 'bottom',
        },
    },
    {
        element: '[data-tour="error-types"]',
        popover: {
            title: 'Most common error types',
            description:
                'Error types ranked by how often students hit them. Click any row to see it over time, the errors behind it, how students got on, and an AI-written summary.',
            side: 'top',
        },
    },
    {
        element: '[data-tour="raw-errors"]',
        popover: {
            title: 'Recurring error messages',
            description:
                "The exact messages students see most often. Students' variable names are removed, so the same mistake is counted together.",
            side: 'left',
        },
    },
    help,
];

const detailSteps: DriveStep[] = [
    {
        popover: {
            title: 'Error type details',
            description: 'This page breaks down one error type for the class and dates you picked.',
        },
    },
    {
        element: '[data-tour="chart"]',
        popover: {
            title: 'How often it happens',
            description: 'How many times students hit this error across the selected dates.',
            side: 'right',
        },
    },
    {
        element: '[data-tour="grouped"]',
        popover: {
            title: "What's behind it",
            description: 'The specific error messages grouped under this type, and how often each one appeared.',
            side: 'left',
        },
    },
    {
        element: '[data-tour="insight"]',
        popover: {
            title: 'Instructor insight',
            description:
                "An AI-written summary of what students are struggling with. Check it against the numbers, especially when it says there's limited data.",
            side: 'top',
        },
    },
    {
        element: '[data-tour="outcomes"]',
        popover: {
            title: 'How students got on',
            description: "How each help session ended, based on the student's final submission.",
            side: 'top',
        },
    },
    {
        element: '[data-tour="detail-dates"]',
        popover: {
            title: 'Change the dates',
            description: 'Change the date range here without going back to the overview.',
            side: 'bottom',
            align: 'end',
        },
    },
    {
        element: '[data-tour="back"]',
        popover: {
            title: 'Back to the overview',
            description: 'Return to the full list of error types.',
            side: 'bottom',
        },
    },
    help,
];

// Starts the tour for the view that's showing. Returns it in case the
// dashboard needs to close it.
export const startInstructorTour = (view: InstructorTourView): Driver => {
    const tour = driver({
        // Nothing can be clicked during the tour. Close it to use the dashboard.
        disableActiveInteraction: true,
        showProgress: true,
        progressText: '{{current}} of {{total}}',
        nextBtnText: 'Next',
        prevBtnText: 'Back',
        doneBtnText: 'Done',
        popoverClass: 'student-tour', // shares the tour styling in index.css
        // Runs however the tour closes. Done on the last step counts as
        // completed, anything else as skipped. Saved to the instructor's account
        // so the tour only starts by itself once.
        onDestroyStarted: () => {
            void saveTourStatus('instructor', tour.hasNextStep() ? 'skipped' : 'completed');
            tour.destroy();
        },
    });
    tour.setSteps(view === 'detail' ? detailSteps : overviewSteps);
    tour.drive();
    return tour;
};