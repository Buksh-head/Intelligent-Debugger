"""API request/response schemas (SQLModel, non-table) for the debugging
assistant API. These are separate from the table models in
app/services/db.py, same library, different job: these describe what
JSON goes over HTTP, db.py's describe what's stored in Postgres.
"""
from sqlmodel import SQLModel


class SubmissionRequest(SQLModel):
    code: str
    expected_behaviour: str = ""
    course: str | None = None
    language: str = "Python"
    session_id: str | None = None  # not persisted client-side yet; generated server-side if omitted


class Finding(SQLModel):
    error_type: str
    line_number: int | None = None
    failing_code_snippet: str = ""


class SubmissionResponse(SQLModel):
    status: str
    findings: list[Finding]


class ExecutionError(SQLModel):
    error_type: str
    message: str
    line_number: int | None = None
    code_snippet: str | None = None


class ExecutionResponse(SQLModel):
    stdout: str
    stderr: str
    exit_code: int | None = None
    status: str | None = None  # Piston returns null status on a clean, successful run
    timed_out: bool
    error: ExecutionError | None = None
    error_id: int | None = None

class HintRequest(SQLModel):
    error_id: int
    finding: Finding
    execution: ExecutionResponse
    student_message: str = "" # What the student said in response to the hint, used for stage classification
    previous_hint: str = "" # The previous hint given to the student, used for stage classification

class HintStage(SQLModel):
    stage: int
    text: str | None = None
    intent: str | None = None # The intent of the student's response to the hint, used for stage classification
    advanced_softly: bool = False # Whether the student advanced softly (e.g., by reaching the vague attempt limit)
    resource_url: str | None = None # The URL of the resource offered to the student, if any
    resource_label: str | None = None # The label of the resource offered to the student, if any
    gate_on_url: bool = False # Whether the resource is gated (i.e., the student must view it before advancing)

class HintResponse(SQLModel):
    status: str
    execution: ExecutionResponse
    finding: Finding
    hints: list[HintStage]


class AnalyticsConcept(SQLModel):
    name: str
    count: int
    percent: float


class AnalyticsError(SQLModel):
    label: str
    count: int


class AnalyticsOutcome(SQLModel):
    label: str
    count: int
    percent: float
    tone: str


class AnalyticsChartPoint(SQLModel):
    label: str
    count: int


class AnalyticsConceptDetail(SQLModel):
    title: str
    description: str
    period_label: str
    chart_points: list[AnalyticsChartPoint]
    grouped_errors: list[AnalyticsError]
    outcomes: list[AnalyticsOutcome]
    topics: list[str]
    note: str


class AnalyticsResponse(SQLModel):
    analysed_sessions: int
    detected_errors: int
    concepts: list[AnalyticsConcept]
    recurring_errors: list[AnalyticsError]
    details: dict[str, AnalyticsConceptDetail]

