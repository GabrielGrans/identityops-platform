from datetime import datetime
from typing import Literal

from pydantic import BaseModel


RangeDays = Literal["7", "30", "90"]
ActivityCategory = Literal["lifecycle", "access", "certification", "entra", "other"]


class Counts(BaseModel):
    active: int
    inactive: int


class Decisions(BaseModel):
    retained: int
    revoked: int


class Reviews(BaseModel):
    pending: int
    decisions: Decisions


class Certification(BaseModel):
    active_campaigns: int
    overdue_campaigns: int
    overdue_items: int
    pending: int
    retained: int
    revoked: int
    superseded: int
    decisions: Decisions


class Security(BaseModel):
    privileged_memberships: int
    inactive_accounts_with_active_groups: int


class RecordedActivity(BaseModel):
    joiners: int
    movers: int
    leavers: int
    revocation_events: int
    failed_entra_syncs: int


class DashboardSummary(BaseModel):
    as_of: datetime
    period_start: datetime
    employees: Counts | None = None
    departments: Counts | None = None
    groups: Counts | None = None
    permissions: Counts | None = None
    pending_requests: int | None = None
    reviews: Reviews | None = None
    certification: Certification | None = None
    certification_available: bool | None = None
    security: Security | None = None
    activity: RecordedActivity | None = None


class ActivityEvent(BaseModel):
    id: int
    created_at: datetime
    category: ActivityCategory
    label: str


class ActivityPage(BaseModel):
    items: list[ActivityEvent]
    next_before_id: int | None
