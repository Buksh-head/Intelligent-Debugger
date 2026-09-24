"""SQLModel table models, one class per Postgres table.

These mirror src/database/schema/schema.sql, which stays the source of
truth applied manually via the Supabase SQL Editor, these classes
describe existing tables, they don't create or migrate them.

Separate from app/models.py: those are API request/response schemas (what
JSON goes over HTTP), these are what's actually stored in the database.
Same library (SQLModel), different job.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, SmallInteger, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Submission(SQLModel, table=True):
    __tablename__ = "submissions"

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(sa_column=Column(PGUUID(as_uuid=False), nullable=False))
    code: str
    code_hash: str
    expected_behaviour: str | None = None
    course: str | None = None
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class ErrorLog(SQLModel, table=True):
    __tablename__ = "error_logs"

    id: int | None = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submissions.id")
    error_type: str
    message: str | None = None
    concept: str | None = None
    line_number: int | None = None
    code_snippet: str | None = None
    hint_stage_reached: int = Field(default=1, sa_column=Column(SmallInteger, nullable=False, server_default="1"))
    vague_attempts_this_stage: int = Field(default=0, sa_column=Column(SmallInteger, nullable=False, server_default="0"))
    pending_resource_concept: str | None = Field(default=None)
    resource_offered: bool = Field(default=False, sa_column=Column(nullable=False, server_default="false"))
    resolved_at: datetime | None = None
    created_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
