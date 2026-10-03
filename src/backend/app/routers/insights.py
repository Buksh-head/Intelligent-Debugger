"""Routes recommended insights per error type (Issue #118) """

from datetime import datetime, timedelta, timezone
from typing import Literal
import logging
logger = logging.getLogger(__name__)


from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlmodel import Session

from app.models import (
    InsightsResponse, InsightStats, 
    AnalyticsChartPoint, AnalyticsError, AnalyticsOutcome
)
from app.services.db import get_engine
from app.services.insight_generator import generate_insights

router = APIRouter(prefix="/api/analytics", tags=["insights"])

DateRange = Literal["today", "last_7_days", "last_month", "semester_2_2026"]
WINDOW_LABELS = {
    "today": "Today",
    "last_7_days": "Last 7 days",
    "last_month": "Last 30 days",
    "semester_2_2026": "Semester 2, 2026"
}
MIN_ERRORS = 3

TYPE_EXPR = "COALESCE(NULLIF(TRIM(el.error_type), ''), 'Unknown error')"

def since_for(date_range: str) -> datetime:
    now = datetime.now(timezone.utc)
    if date_range == "semester_2_2026":
        return datetime(2026, 7, 27, tzinfo=timezone.utc)
    if date_range == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_range == "last_month":
        return now - timedelta(days=30)
    return now - timedelta(days=7)

def _percent(count: int, total: int) -> float:
    return round(count * 100/ total, 1) if total else 0.0

def _build_stats(error_type: str, since, course: str|None, window_label:str) -> InsightStats:
    """This function builds the data necessary for generating teaching recommendations using SQL queries to fetch specific rows.
        Returns an InsightStats data class, ready to be used by generate_insights().
    """
    where = f"WHERE el.created_at >= :since AND {TYPE_EXPR} = :error_type"
    params: dict = {"since": since, "error_type": error_type}
    if course:
        where += " AND s.course = :course"
        params["course"] = course

    base = "FROM error_logs el JOIN submissions s ON s.id = el.submission_id"

    with Session(get_engine()) as session:
        totals = session.execute(text(f"""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT s.session_id) AS sessions,
                   COUNT(*) FILTER (WHERE el.resolved_at IS NOT NULL) AS resolved,
                   COUNT(*) FILTER (WHERE el.resolved_at IS NULL AND el.hint_stage_reached > 1) AS attempted,
                   COUNT(*) FILTER (WHERE el.resolved_at IS NULL AND el.hint_stage_reached = 1) AS untried
            {base} {where}
        """), params).one()

        daily_rows = session.execute(text(f"""
            SELECT DATE_TRUNC('day', el.created_at) AS day, COUNT(*) AS count
            {base} {where}
            GROUP BY 1
            ORDER BY 1
        """), params).all()

        message_rows = session.execute(text(f"""
            SELECT COALESCE(NULLIF(TRIM(el.message), ''), {TYPE_EXPR}) AS label,
                   COUNT(*) AS count
            {base} {where}
            GROUP BY 1
            ORDER BY count DESC, label
            LIMIT 10
        """), params).all()

        concept_rows = session.execute(text(f"""
            SELECT TRIM(el.concept) AS label, COUNT(*) AS count
            {base} {where} AND NULLIF(TRIM(el.concept), '') IS NOT NULL
            GROUP BY 1
            ORDER BY count DESC, label
            LIMIT 5
        """), params).all()

    total = totals.total

    return InsightStats(
        error_type=error_type,
        data_window=window_label,
        total_errors=total,
        distinct_sessions=totals.sessions,
        daily_counts=[
            AnalyticsChartPoint(label=row.day.strftime("%b %d"), count=row.count)
            for row in daily_rows
        ],
        message_breakdown=[
        AnalyticsError(label=row.label, count=row.count) for row in message_rows
        ],
        outcomes=[
            AnalyticsOutcome(label="Resolved", count=totals.resolved,
                             percent=_percent(totals.resolved, total), tone="resolved"),
            AnalyticsOutcome(label="Attempted but unresolved", count=totals.attempted,
                             percent=_percent(totals.attempted, total), tone="attempted"),
            AnalyticsOutcome(label="No recorded retry", count=totals.untried,
                             percent=_percent(totals.untried, total), tone="untried"),
        ],
        related_concepts=[
            AnalyticsError(label=row.label, count=row.count) for row in concept_rows
        ],
    )

        
@router.get("/insights/{error_type}", response_model=InsightsResponse)
def print_insights( 
     error_type: str,
    date_range: DateRange = Query("last_7_days"),
    course: str | None = Query(None),
) -> InsightsResponse:
    stats = _build_stats(error_type, since_for(date_range), course, WINDOW_LABELS[date_range])
    if stats.total_errors < MIN_ERRORS:
        return InsightsResponse(
                    error_type=error_type,
                    summary="Number of errors for this error type is insufficient.",
                    low_data=True,
                    generated=False
                )

    try:
        return generate_insights(stats)
    except Exception:
        logger.exception("Insight generation failed for %s", error_type)
        return InsightsResponse(
            error_type=error_type,
            summary= "Insight generation is unavailable at the moment, please try again.",
            low_data=False,
            generated=False
        )