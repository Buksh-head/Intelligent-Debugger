"""Privacy-preserving aggregate queries for the instructor dashboard.

The frontend calls ``GET /api/analytics/cohort`` through
``src/frontend/src/api.ts``. This router converts the selected date range and
course into aggregate database queries, then returns the shape consumed by
``InstructorDashboard.tsx``:

* ``analysed_sessions`` and ``detected_errors`` populate the overview cards.
* ``concepts`` populates the selectable list of common error types.
* ``recurring_errors`` populates the recurring raw-error list.
* ``details`` supplies the chart, grouped errors, and outcome breakdown for a
  selected concept.

Only aggregate counts and labels are returned; submitted code and session IDs
are not included in the response.
"""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import text
from sqlmodel import Session

from app.models import (
    AnalyticsConcept,
    AnalyticsConceptDetail,
    AnalyticsChartPoint,
    AnalyticsError,
    AnalyticsOutcome,
    AnalyticsResponse,
)
from app.services.db import get_engine

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _percent(count: int, total: int) -> float:
    return round(count * 100 / total, 1) if total else 0.0


@router.get("/cohort", response_model=AnalyticsResponse)
def get_cohort_analytics(
    date_range: Literal[
        "today",
        "last_7_days",
        "last_month",
        "semester_2_2026",
    ] = Query("last_7_days"),
    course: str | None = Query(None),
) -> AnalyticsResponse:
    """Build the complete dataset used by the instructor dashboard.

    ``InstructorDashboard`` requests this endpoint whenever its course or
    date-range filter changes. Selecting an error concept does not make a new
    request; the component reads that concept's entry from ``details``.
    """

    now = datetime.now(timezone.utc)

    # Convert the dashboard's friendly time-range option into one UTC
    # boundary so every aggregate query uses the same period.
    if date_range == "semester_2_2026":
        since = datetime(2026, 7, 27, tzinfo=timezone.utc)
    elif date_range == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == "last_month":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(days=7)

    params = {"since": since.date(), "course": course}
    course_filter = " AND c.course = :course" if course else ""

    # The optional course clause is reused by each query while the values
    # remain parameterised to avoid putting user input into SQL.
    engine = get_engine()

    # Each database query gets its own Session because SQLAlchemy Sessions
    # must not be shared between concurrent threads.

    # Query 1: add the daily submission and error counters for the selected
    # period. These totals become the overview session and error cards.
    def fetch_counts():
        with Session(engine) as session:
            return session.execute(
                text(f"""
                    SELECT
                        (
                            SELECT COALESCE(SUM(c.submission_count), 0)::bigint
                            FROM submission_counts c
                            WHERE c.day >= :since{course_filter}
                        ) AS session_count,
                        (
                            SELECT COALESCE(SUM(c.error_count), 0)::bigint
                            FROM error_counts c
                            WHERE c.day >= :since{course_filter}
                        ) AS error_count
                    """),
                params,
            ).one()

    # Query 2: group errors by error type, count each type, and calculate
    # percentages later. The sorted rows become the common-concepts list.
    def fetch_concepts():
        with Session(engine) as session:
            return session.execute(
                text("""
                    SELECT
                        COALESCE(
                            NULLIF(TRIM(c.error_type), ''),
                            'Unknown error'
                        ) AS name,
                        SUM(c.error_count)::bigint AS count
                    FROM error_counts c
                    WHERE c.day >= :since{course_filter}
                    GROUP BY 1
                    ORDER BY count DESC, name
                    """.format(course_filter=course_filter)),
                params,
            ).all()

    # Query 3: find the ten most frequent raw error messages. This gives
    # instructors a quick view of the repeated messages behind the concepts.
    def fetch_recurring():
        with Session(engine) as session:
            return session.execute(
                text("""
                    SELECT
                        COALESCE(c.message, c.error_type) AS label,
                        SUM(c.error_count)::bigint AS count
                    FROM error_counts c
                    WHERE c.day >= :since{course_filter}
                    GROUP BY 1
                    ORDER BY count DESC, label
                    LIMIT 10
                    """.format(course_filter=course_filter)),
                params,
            ).all()

    # Query 4: group each error type with its individual messages. These
    # rows populate the grouped-errors section of a concept detail view.
    def fetch_details():
        with Session(engine) as session:
            return session.execute(
                text("""
                    SELECT
                        COALESCE(
                            NULLIF(TRIM(c.error_type), ''),
                            'Unknown error'
                        ) AS concept,
                        COALESCE(c.message, c.error_type) AS label,
                        SUM(c.error_count)::bigint AS count
                    FROM error_counts c
                    WHERE c.day >= :since{course_filter}
                    GROUP BY 1, 2
                    ORDER BY 1, count DESC, 2
                    """.format(course_filter=course_filter)),
                params,
            ).all()

    # Query 5: group each error type by day and format the date label. The
    # frontend uses these rows to draw the error-frequency bar chart.
    def fetch_chart():
        with Session(engine) as session:
            return session.execute(
                text("""
                    SELECT
                        COALESCE(
                            NULLIF(TRIM(c.error_type), ''),
                            'Unknown error'
                        ) AS concept,
                        TO_CHAR(c.day, 'Mon DD') AS label,
                        SUM(c.error_count)::bigint AS count,
                        c.day AS day
                    FROM error_counts c
                    WHERE c.day >= :since{course_filter}
                    GROUP BY 1, 2, 4
                    ORDER BY 1, 4
                    """.format(course_filter=course_filter)),
                params,
            ).all()

    # Query 6: count resolved, attempted, and untried outcomes for each
    # error type. These counts become the outcome percentages and bars.
    def fetch_outcomes():
        with Session(engine) as session:
            return session.execute(
                text("""
                    SELECT
                        COALESCE(
                            NULLIF(TRIM(c.error_type), ''),
                            'Unknown error'
                        ) AS concept,
                        COALESCE(SUM(c.error_count) FILTER (
                            WHERE c.outcome = 'resolved'
                        ), 0)::bigint AS resolved,
                        COALESCE(SUM(c.error_count) FILTER (
                            WHERE c.outcome = 'attempted'
                        ), 0)::bigint AS attempted,
                        COALESCE(SUM(c.error_count) FILTER (
                            WHERE c.outcome = 'untried'
                        ), 0)::bigint AS untried
                    FROM error_counts c
                    WHERE c.day >= :since{course_filter}
                    GROUP BY 1
                    """.format(course_filter=course_filter)),
                params,
            ).all()

    # These queries are independent, so run them concurrently rather than
    # waiting for each network/database round trip sequentially.
    with ThreadPoolExecutor(max_workers=6) as executor:
        counts_future = executor.submit(fetch_counts)
        concepts_future = executor.submit(fetch_concepts)
        recurring_future = executor.submit(fetch_recurring)
        details_future = executor.submit(fetch_details)
        chart_future = executor.submit(fetch_chart)
        outcomes_future = executor.submit(fetch_outcomes)

        counts = counts_future.result()
        concept_rows = concepts_future.result()
        recurring_rows = recurring_future.result()
        detail_rows = details_future.result()
        chart_rows = chart_future.result()
        outcome_rows = outcomes_future.result()

    # These top-level values become the overview cards in
    # InstructorDashboard.tsx.
    session_count = counts.session_count
    error_count = counts.error_count

    # Turn database rows into the response models expected by the dashboard.
    concepts = [
        AnalyticsConcept(
            name=row.name,
            count=row.count,
            percent=_percent(row.count, error_count),
        )
        for row in concept_rows
    ]

    grouped: dict[str, list[AnalyticsError]] = defaultdict(list)

    for row in detail_rows:
        grouped[row.concept].append(
            AnalyticsError(
                label=row.label,
                count=row.count,
            )
        )

    charted: dict[str, list[AnalyticsChartPoint]] = defaultdict(list)

    for row in chart_rows:
        charted[row.concept].append(
            AnalyticsChartPoint(
                label=row.label,
                count=row.count,
            )
        )

    details: dict[str, AnalyticsConceptDetail] = {}
    outcome_map = {row.concept: row for row in outcome_rows}

    # Combine the separate detail, chart, and outcome queries into one
    # detail object for each error concept shown in the dashboard.
    for concept in concepts:
        outcome = outcome_map.get(concept.name)

        total = concept.count
        resolved = outcome.resolved if outcome else 0
        attempted = outcome.attempted if outcome else 0
        untried = outcome.untried if outcome else total

        details[concept.name] = AnalyticsConceptDetail(
            title=concept.name,
            description=(
                f"{concept.count} debugging-assistant sessions "
                f"involving {concept.name.lower()} errors"
            ),
            period_label="Recorded errors in the selected dataset",
            chart_points=charted[concept.name],
            grouped_errors=grouped[concept.name],
            outcomes=[
                AnalyticsOutcome(
                    label="Resolved",
                    count=resolved,
                    percent=_percent(resolved, total),
                    tone="resolved",
                ),
                AnalyticsOutcome(
                    label="Attempted but unresolved",
                    count=attempted,
                    percent=_percent(attempted, total),
                    tone="attempted",
                ),
                AnalyticsOutcome(
                    label="No recorded retry",
                    count=untried,
                    percent=_percent(untried, total),
                    tone="untried",
                ),
            ],
            topics=[],
            note=(
                "These are aggregated records only. No student names, "
                "IDs, submitted code or individual session histories "
                "are displayed."
            ),
        )

    # The API wrapper in src/frontend/src/api.ts deserialises this response
    # into AnalyticsResponse, which InstructorDashboard stores in `analytics`.
    return AnalyticsResponse(
        analysed_sessions=session_count,
        detected_errors=error_count,
        concepts=concepts,
        recurring_errors=[
            AnalyticsError(
                label=row.label,
                count=row.count,
            )
            for row in recurring_rows
        ],
        details=details,
    )
