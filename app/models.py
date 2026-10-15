"""SQLModel tables + API schemas."""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy import ARRAY, CheckConstraint, DateTime, Text, func
from sqlmodel import Field, SQLModel


class StrategyType(str, Enum):
    TARGETED = "Targeted"
    SPRAYED = "Sprayed"


class ApplicationStatus(str, Enum):
    APPLIED = "Applied"
    SCREENING = "Screening"
    TECHNICAL = "Technical"
    OFFER = "Offer"
    REJECTED = "Rejected"


STRATEGY_VALUES = tuple(s.value for s in StrategyType)
STATUS_VALUES = tuple(s.value for s in ApplicationStatus)


class ApplicationBase(SQLModel):
    company_name: str = Field(max_length=100, index=True)
    job_title: str = Field(max_length=100, index=True)
    job_link: Optional[str] = Field(default=None, sa_type=Text)
    date_applied: date = Field(default_factory=date.today, index=True)
    strategy_type: str = Field(default=StrategyType.TARGETED.value, max_length=20, index=True)
    status: str = Field(default=ApplicationStatus.APPLIED.value, max_length=30, index=True)
    salary_min: Optional[int] = Field(default=None, index=True)
    salary_max: Optional[int] = Field(default=None, index=True)
    next_follow_up: Optional[date] = Field(default=None, index=True)
    tech_stack: List[str] = Field(default_factory=list, sa_type=ARRAY(Text))
    notes: Optional[str] = Field(default=None, sa_type=Text)
    # CV (path set by the upload endpoint, not the create form)
    cv_path: Optional[str] = Field(default=None, sa_type=Text)
    cv_filename: Optional[str] = Field(default=None, max_length=255)

    # Where the application came from (LinkedIn, Referral, etc.)
    # Derived from job_link at create/update if not set explicitly.
    source: Optional[str] = Field(default=None, max_length=50, index=True)

    # Contact (separate fields, not a blob)
    contact_name: Optional[str] = Field(default=None, max_length=100)
    contact_email: Optional[str] = Field(default=None, max_length=200)

    # Set when status becomes Rejected
    rejection_reason: Optional[str] = Field(default=None, sa_type=Text)


class Application(ApplicationBase, table=True):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "strategy_type IN ('Targeted', 'Sprayed')",
            name="ck_applications_strategy_type",
        ),
        CheckConstraint(
            "status IN ('Applied', 'Screening', 'Technical', 'Offer', 'Rejected')",
            name="ck_applications_status",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )

    # Auto-stamped by the API when status transitions. Never typed by the user.
    # These are write-once and never cleared, so historical analytics stay intact.
    first_response_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    first_interview_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    offer_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))
    rejected_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))

    # Set on every status change. Used by the sweep as the "time in current status" clock.
    status_changed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))

    # Null = active. Non-null = archived. Auto-set on Rejected, auto-cleared on leaving Rejected.
    archived_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(SQLModel):
    company_name: Optional[str] = Field(default=None, max_length=100)
    job_title: Optional[str] = Field(default=None, max_length=100)
    job_link: Optional[str] = Field(default=None, sa_type=Text)
    date_applied: Optional[date] = None
    strategy_type: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = Field(default=None, max_length=30)
    salary_min: Optional[int] = Field(default=None, index=True)
    salary_max: Optional[int] = Field(default=None, index=True)
    next_follow_up: Optional[date] = None
    tech_stack: Optional[List[str]] = Field(default=None, sa_type=ARRAY(Text))
    notes: Optional[str] = Field(default=None, sa_type=Text)
    cv_path: Optional[str] = Field(default=None, sa_type=Text)
    cv_filename: Optional[str] = Field(default=None, max_length=255)
    source: Optional[str] = Field(default=None, max_length=50)
    contact_name: Optional[str] = Field(default=None, max_length=100)
    contact_email: Optional[str] = Field(default=None, max_length=200)
    rejection_reason: Optional[str] = Field(default=None, sa_type=Text)
    archived_at: Optional[datetime] = None


class ApplicationRead(ApplicationBase):
    id: int
    created_at: datetime
    first_response_at: Optional[datetime] = None
    first_interview_at: Optional[datetime] = None
    offer_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    status_changed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None