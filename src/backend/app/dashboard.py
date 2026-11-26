"""The instructor dashboard: cohort error counts and an AI teaching insight per error type.

The team's routes and queries, kept the same so InstructorDashboard.tsx works
unchanged. Two differences:

* Both routes now need an instructor login (the team's version left them open,
  their risk R15).
* The insight is written by the same model as the hints (Claude or Gemini,
  debugger/providers.py) instead of Groq.

Counts come from the submission_counts and error_counts views, which add the
daily counts kept after students delete sessions. Only aggregate counts and
cleaned messages are returned; no code, session IDs or names. Logic errors
(wrong output) show up as the error type "LogicError", timeouts as "Timeout".
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import Session

from app.auth import Account, current_instructor
from app.db import get_engine
from debugger.providers import HintModel, default_hint_model

log = logging.getLogger("debugger.dashboard")

router = APIRouter(prefix="/api/analytics", tags=["instructor-dashboard"])

DateRange = Literal["today", "last_7_days", "last_month", "semester_2_2026"]
WINDOW_LABELS = {
    "today": "Today",
    "last_7_days": "Last 7 days",
    "last_month": "Last 30 days",
    "semester_2_2026": "Semester 2, 2026",
}
MIN_ERRORS = 3


# === Schemas (mirrored in frontend/src/types.ts) ===


class AnalyticsConcept(BaseModel):
    name: str
    count: int
    percent: float


class AnalyticsError(BaseModel):
    label: str
    count: int


class AnalyticsOutcome(BaseModel):
    label: str
    count: int
    percent: float
    tone: str


class AnalyticsChartPoint(BaseModel):
    label: str
    count: int


class AnalyticsConceptDetail(BaseModel):
    title: str
    description: str
    period_label: str
    chart_points: list[AnalyticsChartPoint]
    grouped_errors: list[AnalyticsError]
    outcomes: list[AnalyticsOutcome]
    topics: list[str]
    note: str


class AnalyticsResponse(BaseModel):
    analysed_sessions: int
    detected_errors: int
    concepts: list[AnalyticsConcept]
    recurring_errors: list[AnalyticsError]
    details: dict[str, AnalyticsConceptDetail]


class InsightStats(BaseModel):
    """What the model is given about one error type. Counts only."""

    error_type: str
    data_window: str
    total_errors: int
    distinct_sessions: int | None = None
    daily_counts: list[AnalyticsChartPoint]
    message_breakdown: list[AnalyticsError]
    outcomes: list[AnalyticsOutcome]
    related_concepts: list[AnalyticsError] = []


class InsightsResponse(BaseModel):
    error_type: str
    summary: str
    low_data: bool = False
    generated: bool = True


class InsightDraft(BaseModel):
    summary: str = Field(description="The teaching insight: exactly three sentences, plain text.")


# === Helpers ===


def _percent(count: int, total: int) -> float:
    return round(count * 100 / total, 1) if total else 0.0


def since_for(date_range: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if date_range == "semester_2_2026":
        return datetime(2026, 7, 27, tzinfo=timezone.utc)
    if date_range == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_range == "last_month":
        return now - timedelta(days=30)
    return now - timedelta(days=7)


def _outcomes(resolved: int, attempted: int, untried: int, total: int) -> list[AnalyticsOutcome]:
    return [
        AnalyticsOutcome(label="Resolved", count=resolved, percent=_percent(resolved, total), tone="resolved"),
        AnalyticsOutcome(label="Attempted but unresolved", count=attempted,
                         percent=_percent(attempted, total), tone="attempted"),
        AnalyticsOutcome(label="No recorded retry", count=untried, percent=_percent(untried, total), tone="untried"),
    ]


_TYPE = "COALESCE(NULLIF(TRIM(c.error_type), ''), 'Unknown error')"


# === Cohort analytics ===


def cohort_analytics(date_range: str, course: str | None) -> AnalyticsResponse:
    params = {"since": since_for(date_range).date(), "course": course}
    where = "WHERE c.day >= :since" + (" AND c.course = :course" if course else "")
    engine = get_engine()

    def query(sql: str):
        # One Session per thread: SQLAlchemy Sessions must not be shared between threads.
        with Session(engine) as db:
            return db.execute(text(sql), params).all()

    queries = {
        "counts": f"""
            SELECT (SELECT COALESCE(SUM(c.submission_count), 0)::bigint FROM submission_counts c {where})
                       AS session_count,
                   (SELECT COALESCE(SUM(c.error_count), 0)::bigint FROM error_counts c {where})
                       AS error_count""",
        "concepts": f"""
            SELECT {_TYPE} AS name, SUM(c.error_count)::bigint AS count
            FROM error_counts c {where}
            GROUP BY 1 ORDER BY count DESC, name""",
        "recurring": f"""
            SELECT COALESCE(c.message, c.error_type) AS label, SUM(c.error_count)::bigint AS count
            FROM error_counts c {where}
            GROUP BY 1 ORDER BY count DESC, label LIMIT 10""",
        "details": f"""
            SELECT {_TYPE} AS concept, COALESCE(c.message, c.error_type) AS label,
                   SUM(c.error_count)::bigint AS count
            FROM error_counts c {where}
            GROUP BY 1, 2 ORDER BY 1, count DESC, 2""",
        "chart": f"""
            SELECT {_TYPE} AS concept, TO_CHAR(c.day, 'Mon DD') AS label,
                   SUM(c.error_count)::bigint AS count, c.day AS day
            FROM error_counts c {where}
            GROUP BY 1, 2, 4 ORDER BY 1, 4""",
        "outcomes": f"""
            SELECT {_TYPE} AS concept,
                   COALESCE(SUM(c.error_count) FILTER (WHERE c.outcome = 'resolved'), 0)::bigint AS resolved,
                   COALESCE(SUM(c.error_count) FILTER (WHERE c.outcome = 'attempted'), 0)::bigint AS attempted,
                   COALESCE(SUM(c.error_count) FILTER (WHERE c.outcome = 'untried'), 0)::bigint AS untried
            FROM error_counts c {where}
            GROUP BY 1""",
    }
    # Independent queries, so they run at the same time instead of one round trip each.
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        futures = {name: pool.submit(query, sql) for name, sql in queries.items()}
        rows = {name: f.result() for name, f in futures.items()}

    [counts] = rows["counts"]
    error_count = counts.error_count
    concepts = [AnalyticsConcept(name=r.name, count=r.count, percent=_percent(r.count, error_count))
                for r in rows["concepts"]]

    grouped: dict[str, list[AnalyticsError]] = defaultdict(list)
    for r in rows["details"]:
        grouped[r.concept].append(AnalyticsError(label=r.label, count=r.count))
    charted: dict[str, list[AnalyticsChartPoint]] = defaultdict(list)
    for r in rows["chart"]:
        charted[r.concept].append(AnalyticsChartPoint(label=r.label, count=r.count))
    outcome_map = {r.concept: r for r in rows["outcomes"]}

    details = {}
    for concept in concepts:
        o = outcome_map.get(concept.name)
        total = concept.count
        details[concept.name] = AnalyticsConceptDetail(
            title=concept.name,
            description=f"{concept.count} debugging-assistant sessions involving {concept.name.lower()} errors",
            period_label="Recorded errors in the selected dataset",
            chart_points=charted[concept.name],
            grouped_errors=grouped[concept.name],
            outcomes=_outcomes(o.resolved if o else 0, o.attempted if o else 0, o.untried if o else total, total),
            topics=[],
            note=("These are aggregated records only. No student names, IDs, submitted code or "
                  "individual session histories are displayed."),
        )

    return AnalyticsResponse(
        analysed_sessions=counts.session_count,
        detected_errors=error_count,
        concepts=concepts,
        recurring_errors=[AnalyticsError(label=r.label, count=r.count) for r in rows["recurring"]],
        details=details,
    )


@router.get("/cohort", response_model=AnalyticsResponse)
async def get_cohort_analytics(
    date_range: DateRange = Query("last_7_days"),
    course: str | None = Query(None),
    _: Account = Depends(current_instructor),
) -> AnalyticsResponse:
    return await run_in_threadpool(cohort_analytics, date_range, course or None)


# === AI insight ===

INSIGHT_SYSTEM_PROMPT = """You are an experienced instructor who teaches first-year programming.
You are given counts about one error type that students hit in a debugging tool: how many errors,
their messages, what happened after (resolved, attempted but unresolved, no recorded retry), the
concepts they were tagged with, and errors per day.

Write a teaching insight for the course staff in exactly three plain-text sentences: what the
pattern suggests students misunderstand, and what to teach or revise.

Rules:
- Only cite numbers that appear in the data. Never make up numbers.
- Days with no errors are left out of the daily counts, so don't describe trends from a few points.
- If total_errors is below 3, reply in one sentence that the evidence is limited, and stop.
- If distinct_sessions is null, don't mention session counts.
- Never mention individual students or sessions.
- error_type "LogicError" means the program ran but printed something other than what the student
  expected; its concepts are the kind of mistake (off_by_one, recursion_base_case, calculation,
  missing_return, other). "Timeout" means the program never finished, usually an endless loop.
"""


def insight_stats(error_type: str, date_range: str, course: str | None) -> InsightStats:
    """Live rows only (deleted sessions keep their daily counts but not their hints or concepts)."""
    where = ("WHERE el.created_at >= :since "
             "AND COALESCE(NULLIF(TRIM(el.error_type), ''), 'Unknown error') = :error_type")
    params: dict = {"since": since_for(date_range), "error_type": error_type}
    if course:
        where += " AND s.course = :course"
        params["course"] = course
    base = "FROM error_logs el JOIN submissions s ON s.id = el.submission_id"

    with Session(get_engine()) as db:
        totals = db.execute(text(f"""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT s.session_id) AS sessions,
                   COUNT(*) FILTER (WHERE el.resolved_at IS NOT NULL) AS resolved,
                   COUNT(*) FILTER (WHERE el.resolved_at IS NULL AND el.hint_stage_reached > 1) AS attempted,
                   COUNT(*) FILTER (WHERE el.resolved_at IS NULL AND el.hint_stage_reached = 1) AS untried
            {base} {where}"""), params).one()
        daily = db.execute(text(f"""
            SELECT DATE_TRUNC('day', el.created_at) AS day, COUNT(*) AS count
            {base} {where} GROUP BY 1 ORDER BY 1"""), params).all()
        messages = db.execute(text(f"""
            SELECT COALESCE(NULLIF(TRIM(normalise_error_message(el.message)), ''), el.error_type) AS label,
                   COUNT(*) AS count
            {base} {where} GROUP BY 1 ORDER BY count DESC, label LIMIT 10"""), params).all()
        concepts = db.execute(text(f"""
            SELECT TRIM(el.concept) AS label, COUNT(*) AS count
            {base} {where} AND NULLIF(TRIM(el.concept), '') IS NOT NULL
            GROUP BY 1 ORDER BY count DESC, label LIMIT 5"""), params).all()

    return InsightStats(
        error_type=error_type,
        data_window=WINDOW_LABELS[date_range],
        total_errors=totals.total,
        distinct_sessions=totals.sessions,
        daily_counts=[AnalyticsChartPoint(label=r.day.strftime("%b %d"), count=r.count) for r in daily],
        message_breakdown=[AnalyticsError(label=r.label, count=r.count) for r in messages],
        outcomes=_outcomes(totals.resolved, totals.attempted, totals.untried, totals.total),
        related_concepts=[AnalyticsError(label=r.label, count=r.count) for r in concepts],
    )


def generate_insight(stats: InsightStats, model: HintModel | None) -> InsightsResponse:
    if model is None:
        return InsightsResponse(error_type=stats.error_type, generated=False,
                                summary="AI insights need a model key (ANTHROPIC_API_KEY or GEMINI_API_KEY).")
    user = (f"Error type: {stats.error_type}\nData window: {stats.data_window}\nStatistics:\n"
            + stats.model_dump_json(indent=2, exclude={"error_type", "data_window"}))
    draft = model.structured(INSIGHT_SYSTEM_PROMPT, user, InsightDraft)
    summary = " ".join(draft.summary.split())
    if not summary:
        raise ValueError("the model returned an empty insight")
    return InsightsResponse(error_type=stats.error_type, summary=summary, low_data=False, generated=True)


def insight_for(error_type: str, date_range: str, course: str | None,
                model_factory: Callable[[], HintModel | None] = default_hint_model) -> InsightsResponse:
    stats = insight_stats(error_type, date_range, course)
    if stats.total_errors < MIN_ERRORS:
        return InsightsResponse(error_type=error_type, summary="Number of errors for this error type is insufficient.",
                                low_data=True, generated=False)
    try:
        return generate_insight(stats, model_factory())
    except Exception:
        log.exception("insight generation failed for %s", error_type)
        return InsightsResponse(error_type=error_type, low_data=False, generated=False,
                                summary="Insight generation is unavailable at the moment, please try again.")


@router.get("/insights/{error_type}", response_model=InsightsResponse)
async def get_insights(
    error_type: str,
    date_range: DateRange = Query("last_7_days"),
    course: str | None = Query(None),
    _: Account = Depends(current_instructor),
) -> InsightsResponse:
    return await run_in_threadpool(insight_for, error_type, date_range, course or None)
