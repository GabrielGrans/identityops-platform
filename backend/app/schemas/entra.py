from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExternalObject(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    object_id: UUID
    display_name: str | None
    present: bool
    last_seen_run_id: int


class ExternalUser(ExternalObject):
    principal_name: str | None
    mail: str | None
    account_enabled: bool | None
    local_employee_id: int | None


class ExternalGroup(ExternalObject):
    security_enabled: bool | None
    local_group_id: int | None


class LinkInput(BaseModel):
    local_id: int | None = Field(ge=1, le=2_147_483_647)


class SyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    finished_at: datetime | None
    error_code: str | None
    users_count: int | None
    groups_count: int | None
    memberships_count: int | None
    skipped_users_count: int | None


class EntraStatus(BaseModel):
    imported_users: int | None = None
    imported_groups: int | None = None
    state: Literal["disabled", "invalid_configuration", "migration_required", "ready", "connected", "error", "sync_running"]
    message: str
    last_success_at: datetime | None = None
    latest_run: SyncRunResponse | None = None


class AccessComparison(BaseModel):
    local_only_group_ids: list[int]
    entra_only_group_ids: list[int]
    unmapped_local_group_ids: list[int]
    unmapped_entra_group_ids: list[str]


class UserAccessResponse(BaseModel):
    user: ExternalUser
    groups: list[ExternalGroup]
    comparison: AccessComparison | None
    snapshot_id: int | None
