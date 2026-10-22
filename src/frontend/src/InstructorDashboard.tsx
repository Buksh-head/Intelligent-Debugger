/**
 * Instructor dashboard. Shows anonymous error stats across the cohort,
 * filtered by course and date range. Clicking an error type opens a
 * detail view with a chart, outcomes and an AI-generated summary.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { getCohortAnalytics, getInsights } from "./api";
import type {
  AnalyticsConcept,
  AnalyticsDateRange,
  AnalyticsResponse,
  InsightsResponse,
} from "./types";
import { type Theme, getInitialTheme, themeStorageKey } from "./theme";
import {
  ArrowLeft,
  ArrowRight,
  CircleHelp,
  LogOut,
  Sun,
  Moon,
  User,
} from "lucide-react";
import { useAuth } from "./auth/useAuth";
import { courses } from "./session/courses";
import { startInstructorTour } from "./tour/instructorTour";
import { hasSeenTour } from "./tour/tourStatus";
const appLogo = "/error-guide-logo.png";
type InstructorDashboardProps = {
  onBack: () => void;
};

// Courses in the class filter, from the same list students pick from.
const courseCodes = courses.map((option) => option.code);

export default function InstructorDashboard({
  onBack,
}: InstructorDashboardProps) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  // The error type being viewed.
  const [selectedConcept, setSelectedConcept] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("concept"),
  );
  const [dateRange, setDateRange] = useState<AnalyticsDateRange>("last_7_days");
  const [course, setCourse] = useState("");
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [insight, setInsight] = useState<InsightsResponse | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [insightError, setInsightError] = useState<string | null>(null);
  const { session } = useAuth();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(themeStorageKey, theme);
  }, [theme]);

  // Update the selected error type when the back/forward button is used.
  useEffect(() => {
    const handlePopState = () => {
      setSelectedConcept(
        new URLSearchParams(window.location.search).get("concept"),
      );
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Reload the stats whenever the course or date range changes.
  useEffect(() => {
    getCohortAnalytics(dateRange, course || undefined)
      .then(setAnalytics)
      .catch((error: unknown) =>
        setAnalyticsError(
          error instanceof Error
            ? error.message
            : "Unable to load cohort analytics.",
        ),
      );
  }, [course, dateRange]);

  // Details for the selected error type. If it has no data in this
  // date range, show an empty view instead of an error.
  const activeConcept = useMemo(() => {
    if (!selectedConcept || !analytics) return null;

    return (
      analytics.details[selectedConcept] ?? {
        title: selectedConcept,
        description: `No records found for ${selectedConcept} in the selected date range.`,
        period_label: "No recorded errors in the selected dataset",
        chart_points: [],
        grouped_errors: [],
        outcomes: [],
        topics: [],
        note: "No records were found for this error type in the selected date range.",
      }
    );
  }, [analytics, selectedConcept]);

  // Starts the tour for whichever view is showing.
  const startTour = () =>
    startInstructorTour(activeConcept ? "detail" : "overview");

  // Start the overview tour by itself the first time an instructor account
  // opens the dashboard, once the stats have loaded so every part is on screen.
  // The ref stops it starting twice when React runs effects twice in development.
  const autoTourStartedRef = useRef(false);
  useEffect(() => {
    if (!analytics || activeConcept || autoTourStartedRef.current) return;
    if (hasSeenTour(session, "instructor")) return;
    autoTourStartedRef.current = true;
    startInstructorTour("overview");
  }, [analytics, activeConcept, session]);

  // Whether the selected error type has records in this date range. Only
  // then is there anything for the AI to summarise.
  const hasConceptDetails = Boolean(
    selectedConcept && analytics?.details[selectedConcept],
  );

  // Get the AI summary for the selected error type.
  useEffect(() => {
    if (!activeConcept || !hasConceptDetails) return;
    const controller = new AbortController();
    const loadInsight = async () => {
      try {
        setInsightLoading(true);
        setInsightError(null);
        setInsight(null);
        setInsight(
          await getInsights(
            activeConcept.title,
            dateRange,
            course,
            controller.signal,
          ),
        );
      } catch (error: unknown) {
        if (axios.isCancel(error)) {
          return;
        }
        setInsightError(
          error instanceof Error
            ? error.message
            : "Unable to generate instructor insight.",
        );
      } finally {
        if (!controller.signal.aborted) {
          setInsightLoading(false);
        }
      }
    };
    loadInsight();
    return () => controller.abort();
  }, [activeConcept, course, dateRange, hasConceptDetails]);

  // An error type with no records gets no summary, so whatever was fetched
  // for the previous one is not shown.
  const shownInsight = hasConceptDetails ? insight : null;
  const shownInsightLoading = hasConceptDetails && insightLoading;
  const shownInsightError = hasConceptDetails ? insightError : null;
  const concepts: AnalyticsConcept[] = analytics?.concepts ?? [];
  const overviewStats = analytics
    ? [
        {
          label: "Analysed sessions",
          value: String(analytics.analysed_sessions),
        },
        { label: "Detected errors", value: String(analytics.detected_errors) },
        {
          label: "Most common concept",
          value: analytics.concepts[0]?.name ?? "None recorded",
        },
      ]
    : [];

  // Bar chart sizing, in SVG units. Only every few labels are shown so
  // they don't overlap.
  const chartPoints = activeConcept?.chart_points ?? [];
  const chartMax = Math.max(...chartPoints.map((point) => point.count), 1);
  const chartWidth = 455;
  const chartHeight = 170;
  const chartLeft = 48;
  const chartTop = 12;
  const chartBottom = chartTop + chartHeight;
  const chartStep =
    chartPoints.length > 0 ? chartWidth / chartPoints.length : chartWidth;
  const barWidth =
    chartPoints.length > 0 ? Math.min(46, Math.max(18, chartStep * 0.62)) : 0;
  const labelStep = Math.max(1, Math.ceil(chartPoints.length / 8));
  const yTicks = Array.from({ length: 5 }, (_, index) =>
    Math.round((chartMax * index) / 4),
  );
  return (
    <div className="min-h-screen w-full bg-base-100 p-5 text-base-content">
      {/* The header identifies the instructor view and contains account controls. */}
      <header className="navbar">
        <div className="flex-1 flex items-center gap-3">
          <img
            src={appLogo}
            alt="Error Guide logo"
            className="h-22 w-22 shrink-0 rounded-box object-contain"
          />
          <div>
            <h1 className="font-mono text-3xl font-semibold tracking-wider text-primary">
              ERROR GUIDE
            </h1>
            <p className="mt-1">Instructor View</p>
          </div>
        </div>
        {/* Replays the dashboard tour for the view that's showing. */}
        <button
          type="button"
          data-tour="help"
          className="btn btn-circle btn-ghost mr-2 h-15 w-15"
          onClick={startTour}
          disabled={!analytics}
          aria-label="Show the dashboard tour"
          title="Show the dashboard tour"
        >
          <CircleHelp size={28} />
        </button>
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
            tabIndex={0}
            className="dropdown-content z-20 mt-3 w-64 rounded-xl border border-base-300 bg-base-100 p-4 shadow-xl"
          >
            {/* Profile summary is shown inside the account dropdown. */}
            <div className="mb-4 flex items-center gap-3 border-b border-base-300 pb-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-content">
                <User size={24} />
              </div>

              <div>
                <div className="font-semibold">Instructor</div>
                <div className="text-sm text-base-content/60">
                  Dashboard account
                </div>
              </div>
            </div>

            {/* The theme button switches between the saved light and dark themes. */}
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="font-medium">Theme</div>
                <div className="text-sm text-base-content/60">
                  {theme === "dark" ? "Dark mode" : "Light mode"}
                </div>
              </div>

              <button
                type="button"
                className="btn btn-sm btn-circle btn-outline"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              >
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
            </div>

            {/* Logging out uses the parent callback to leave the protected dashboard. */}
            <button
              type="button"
              className="btn btn-error w-full"
              onClick={onBack}
            >
              <LogOut size={16} />
              Log out
            </button>
          </div>
        </div>
      </header>
      <div className="flex min-h-0">
        <main className="flex-1 bg-base-100 px-0 py-4.5 min-[981px]:pb-4 min-[981px]:pt-0">
          {/* The main area shows an error, loading state, selected-concept detail,
              or the overview depending on the current data and selection. */}
          {analyticsError ? (
            <p className="rounded-xl border border-error/30 bg-error/10 p-5 text-error-content">
              {analyticsError}
            </p>
          ) : !analytics ? (
            <p className="rounded-xl border border-base-300 bg-base-200 p-5 text-base-content/70">
              Loading cohort analytics...
            </p>
          ) : activeConcept ? (
            <>
              {/* Detail view for the error type selected from the overview. */}
              <div className="mb-5.5 grid gap-4 min-[981px]:grid-cols-[1fr_auto_1fr] min-[981px]:items-start min-[981px]:gap-5">
                <div className="text-left min-[981px]:col-start-2 min-[981px]:row-start-1 min-[981px]:text-center">
                  <h1 className="text-[clamp(2rem,2.4vw,3rem)] font-bold leading-tight tracking-tight">
                    {activeConcept.title}
                  </h1>
                  <p className="mt-2 text-base text-base-content/65">
                    {activeConcept.description}
                  </p>
                </div>
                <div
                  data-tour="back"
                  className="flex flex-wrap items-end gap-3.5 min-[981px]:col-start-1 min-[981px]:row-start-1 min-[981px]:pt-5.5"
                >
                  {/* Clear the URL selection and return to the overview list. */}
                  <button
                    type="button"
                    className="btn btn-outline"
                    onClick={() => {
                      window.history.replaceState(
                        null,
                        "",
                        window.location.pathname,
                      );
                      setSelectedConcept(null);
                    }}
                  >
                    <ArrowLeft size={16} aria-hidden="true" />
                    Back to overview
                  </button>
                </div>

                <div
                  data-tour="detail-dates"
                  className="flex min-w-35 flex-col gap-1.5 min-[981px]:col-start-3 min-[981px]:row-start-1 min-[981px]:justify-self-end"
                >
                  <label className="text-xs text-base-content/70">
                    Date range
                  </label>
                  <select
                    className="select select-bordered h-12 w-full bg-base-100 text-base-content"
                    value={dateRange}
                    onChange={(event) =>
                      setDateRange(event.target.value as AnalyticsDateRange)
                    }
                  >
                    <option value="today">Today</option>
                    <option value="last_7_days">Last 7 days</option>
                    <option value="last_month">Last month</option>
                    <option value="semester_2_2026">2026 Sem 2</option>
                  </select>
                </div>
              </div>
              {/* The chart displays how often this error type occurred over time. */}
              <div className="grid gap-4.5 min-[981px]:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                <div
                  data-tour="chart"
                  className="min-h-100 rounded-xl border border-base-300 bg-base-200 p-5 pb-4.5"
                >
                  <div className="mb-1.5 text-[1.05rem] font-semibold">
                    Error frequency over time
                  </div>
                  {chartPoints.length === 0 ? (
                    <p className="mt-4 text-sm text-base-content/60">
                      No records found
                    </p>
                  ) : (
                    <svg
                      viewBox="0 0 520 230"
                      className="mt-3 block h-80 w-full"
                      role="img"
                      aria-label="Error frequency over time"
                    >
                      {yTicks.map((tick, index) => {
                        const y = chartBottom - (index / 4) * chartHeight;
                        return (
                          <g key={tick}>
                            <line
                              x1={chartLeft}
                              x2={chartLeft + chartWidth}
                              y1={y}
                              y2={y}
                              stroke="currentColor"
                              opacity="0.2"
                            />
                            <text
                              x={chartLeft - 8}
                              y={y + 4}
                              textAnchor="end"
                              fill="currentColor"
                              className="text-[10px]"
                            >
                              {tick}
                            </text>
                          </g>
                        );
                      })}
                      <line
                        x1={chartLeft}
                        x2={chartLeft}
                        y1={chartTop}
                        y2={chartBottom}
                        stroke="currentColor"
                        opacity="0.55"
                      />
                      <line
                        x1={chartLeft}
                        x2={chartLeft + chartWidth}
                        y1={chartBottom}
                        y2={chartBottom}
                        stroke="currentColor"
                        opacity="0.55"
                      />
                      {chartPoints.map((point, index) => {
                        const x = chartLeft + (index + 0.5) * chartStep;
                        const barHeight =
                          (point.count / chartMax) * chartHeight;
                        return (
                          <g key={`${point.label}-${index}`}>
                            <rect
                              x={x - barWidth / 2}
                              y={chartBottom - barHeight}
                              width={barWidth}
                              height={barHeight}
                              rx="3"
                              fill="currentColor"
                              className="text-primary"
                              opacity="0.9"
                            />
                            {(index % labelStep === 0 ||
                              index === chartPoints.length - 1) && (
                              <text
                                x={x}
                                y={chartBottom + 18}
                                textAnchor="middle"
                                fill="currentColor"
                                className="text-[10px]"
                              >
                                {point.label}
                              </text>
                            )}
                          </g>
                        );
                      })}
                    </svg>
                  )}
                </div>
                <div
                  data-tour="grouped"
                  className="min-h-65 rounded-xl border border-base-300 bg-base-200 p-5 pb-4.5"
                >
                  <div className="mb-1.5 text-[1.05rem] font-semibold">
                    Errors grouped under this type
                  </div>
                  <ul className="mt-3.5 max-h-65 overflow-y-auto pr-2 list-none p-0">
                    {activeConcept.grouped_errors.length === 0 ? (
                      <li className="py-2.5 text-sm text-base-content/60">
                        No records found
                      </li>
                    ) : (
                      activeConcept.grouped_errors.map((item) => (
                        <li
                          key={item.label}
                          className="flex items-center justify-between gap-4 border-b border-base-300 py-2.5 text-base-content/80 last:border-b-0"
                        >
                          <span>{item.label}</span>
                          <strong>{item.count}</strong>
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              </div>
              <div className="mt-4.5 grid gap-4.5 min-[981px]:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                {/* This panel displays the optional AI-generated explanation. */}
                <div
                  data-tour="insight"
                  className="rounded-xl border border-primary/30 bg-base-200 p-5 pb-4.5"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="mb-1.5 text-[1.05rem] font-semibold">
                        Instructor insight
                      </div>
                    </div>
                    {shownInsight?.generated && (
                      <span className="shrink-0 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs text-primary">
                        AI generated
                      </span>
                    )}
                  </div>
                  {shownInsightLoading ? (
                    <div className="mt-4 flex items-center gap-3 text-sm text-base-content/60">
                      <span
                        className="loading loading-spinner loading-sm"
                        aria-hidden="true"
                      />
                      Generating insight...
                    </div>
                  ) : shownInsightError ? (
                    <p className="mt-4 rounded-lg border border-error/30 bg-error/10 p-3 text-sm text-error-content">
                      {shownInsightError}
                    </p>
                  ) : shownInsight ? (
                    <div className="mt-4 rounded-lg border border-base-300 bg-base-100 p-4">
                      <p className="m-0 text-[0.95rem] leading-7 text-base-content/85">
                        {shownInsight.summary}
                      </p>
                      {shownInsight.low_data && (
                        <p className="mt-3 mb-0 text-xs text-base-content/50">
                          Limited data is available for this error type in the
                          selected window.
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="mt-4 text-sm text-base-content/60">
                      Select an error type to generate an instructor insight.
                    </p>
                  )}
                </div>

                {/* These bars show whether sessions ended resolved, attempted, or untried. */}
                <div
                  data-tour="outcomes"
                  className="flex h-full flex-col rounded-xl border border-base-300 bg-base-200 p-5 pb-4.5"
                >
                  <div className="mb-1.5 text-[1.05rem] font-semibold">
                    Debugging assistance outcomes
                  </div>
                  <p className="m-0 text-xs text-base-content/60">
                    Outcome of the final recorded submission in each assistance
                    session
                  </p>
                  <div className="mt-4.5 flex h-7 overflow-hidden rounded-lg border border-base-300 bg-base-100">
                    {activeConcept.outcomes.map((item) => (
                      <div
                        key={item.label}
                        className="h-full"
                        style={{ width: `${item.percent}%` }}
                      >
                        <div
                          className={`h-full ${item.tone === "resolved" ? "bg-green-600/90" : item.tone === "attempted" ? "bg-amber-500/90" : "bg-red-600/90"}`}
                        />
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 flex flex-1 flex-col justify-center gap-2">
                    {activeConcept.outcomes.length === 0 ? (
                      <p className="text-sm text-base-content/60">
                        No records found
                      </p>
                    ) : (
                      activeConcept.outcomes.map((item) => (
                        <div
                          key={item.label}
                          className="flex items-center justify-between gap-3 rounded-lg border border-base-300 bg-base-100/60 px-3 py-2 text-xs text-base-content/80"
                        >
                          <span className="flex min-w-0 items-center gap-2">
                            <span
                              className={`h-2 w-2 shrink-0 rounded-full ${item.tone === "resolved" ? "bg-green-500" : item.tone === "attempted" ? "bg-amber-500" : "bg-red-500"}`}
                            />
                            <span className="truncate">{item.label}</span>
                          </span>
                          <span className="shrink-0">
                            <strong
                              className={`text-lg font-semibold tracking-tight ${item.tone === "resolved" ? "text-green-400/90" : item.tone === "attempted" ? "text-amber-300/90" : "text-red-400/90"}`}
                            >
                              {item.count}
                            </strong>
                            <span className="ml-1 text-base-content/60">
                              • {item.percent}%
                            </span>
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <>
              {/* The overview provides filters, headline statistics, and selectable error types. */}
              <div className="mb-5.5 grid gap-4 min-[981px]:flex min-[981px]:items-start min-[981px]:justify-between min-[981px]:gap-5">
                <div className="flex-1">
                  <h1 className="text-[clamp(2rem,2.4vw,3rem)] font-bold leading-tight tracking-tight">
                    {course
                      ? `${course} cohort error overview`
                      : "All Cohort error overview"}
                  </h1>
                </div>
                <div
                  data-tour="filters"
                  className="flex flex-wrap items-end gap-3.5"
                >
                  {/* Changing either filter reloads the cohort data through the effect above. */}
                  <div className="flex min-w-35 flex-col gap-1.5">
                    <label className="text-xs text-base-content/70">
                      Class
                    </label>
                    <select
                      className="select select-bordered h-12 w-full bg-base-100 text-base-content"
                      value={course}
                      onChange={(event) => setCourse(event.target.value)}
                    >
                      <option value="">All classes</option>
                      {courseCodes.map((courseCode) => (
                        <option key={courseCode} value={courseCode}>
                          {courseCode}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex min-w-35 flex-col gap-1.5">
                    <label className="text-xs text-base-content/70">
                      Date range
                    </label>
                    <select
                      className="select select-bordered h-12 w-full bg-base-100 text-base-content"
                      value={dateRange}
                      onChange={(event) =>
                        setDateRange(event.target.value as AnalyticsDateRange)
                      }
                    >
                      <option value="today">Today</option>
                      <option value="last_7_days">Last 7 days</option>
                      <option value="last_month">Last month</option>
                      <option value="semester_2_2026">2026 Sem 2</option>
                    </select>
                  </div>
                </div>
              </div>
              <div
                data-tour="stats"
                className="mb-5 grid gap-4.5 min-[981px]:grid-cols-3"
              >
                {overviewStats.map((stat) => (
                  <div
                    key={stat.label}
                    className="flex min-h-27.5 flex-col justify-center rounded-xl border border-base-300 bg-base-200 px-5 py-4.5"
                  >
                    <div className="mb-2 text-sm text-base-content/70">
                      {stat.label}
                    </div>
                    <div className="text-[clamp(1.6rem,2vw,2.5rem)] font-semibold leading-tight tracking-tight">
                      {stat.value}
                    </div>
                  </div>
                ))}
              </div>
              <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
                <div
                  data-tour="error-types"
                  className="flex h-[calc(100vh-420px)] min-h-100 flex-col rounded-xl border border-base-300 bg-base-200 p-5 pb-4.5"
                >
                  <div>
                    <div>
                      <div className="mb-1.5 text-[1.05rem] font-semibold">
                        Most common error types
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 h-full overflow-y-auto space-y-1.5 pr-2">
                    {/* Each error type updates the URL and opens its detail view. */}
                    {concepts.length === 0 ? (
                      <p className="py-2.5 text-sm text-base-content/60">
                        No records found
                      </p>
                    ) : (
                      concepts.map((concept) => (
                        <button
                          key={concept.name}
                          type="button"
                          className="grid w-full cursor-pointer grid-cols-[minmax(110px,180px)_minmax(0,1fr)_78px_112px] items-center gap-3 rounded-lg border border-base-300 bg-base-100 px-3 py-2.5 text-left text-inherit transition hover:border-primary/50 hover:bg-base-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                          aria-label={`View details for ${concept.name}`}
                          onClick={() => {
                            const params = new URLSearchParams(
                              window.location.search,
                            );
                            params.set("concept", concept.name);
                            window.history.pushState(
                              null,
                              "",
                              `${window.location.pathname}?${params.toString()}`,
                            );
                            setSelectedConcept(concept.name);
                          }}
                        >
                          <span className="font-medium text-base-content/90">
                            {concept.name}
                          </span>
                          <span className="h-3 w-full overflow-hidden rounded-full border border-base-300 bg-base-200">
                            <span
                              className="block h-full rounded-full bg-primary/80"
                              style={{ width: `${concept.percent}%` }}
                            />
                          </span>
                          <span className="w-full whitespace-nowrap text-right text-xs text-base-content/70">
                            {concept.count} • {concept.percent}%
                          </span>
                          <span className="flex w-full items-center justify-end gap-1 whitespace-nowrap text-right text-base font-medium text-primary">
                            See details{" "}
                            <ArrowRight size={16} aria-hidden="true" />
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <div
                    data-tour="raw-errors"
                    className="flex h-[calc(100vh-420px)] min-h-100 flex-col rounded-xl border border-base-300 bg-base-200 p-5 pb-4.5"
                  >
                    <div className="mb-1.5 text-[1.05rem] font-semibold">
                      Recurring raw errors
                    </div>

                    <ul className="mt-3.5 min-h-0 flex-1 overflow-y-auto pr-2 list-none p-0">
                      {/* This list shows the most frequent raw error messages in the filtered data. */}
                      {analytics.recurring_errors.length === 0 ? (
                        <li className="py-2.5 text-sm text-base-content/60">
                          No records found
                        </li>
                      ) : (
                        analytics.recurring_errors.map((item) => (
                          <li
                            key={item.label}
                            className="flex items-center justify-between gap-4 border-b border-base-300 py-2.5 text-base-content/80 last:border-b-0"
                          >
                            <span>{item.label}</span>
                            <strong>{item.count}</strong>
                          </li>
                        ))
                      )}
                    </ul>
                  </div>
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
