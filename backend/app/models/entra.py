from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.app.models.employee import Employee
from backend.app.models.group import Group


class EntraBase(DeclarativeBase):
    """Integration tables are created by explicit migrations."""


class EntraSyncRun(EntraBase):
    __tablename__ = "entra_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey(Employee.id))
    active_slot: Mapped[int | None] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    users_count: Mapped[int | None]
    groups_count: Mapped[int | None]
    memberships_count: Mapped[int | None]
    skipped_users_count: Mapped[int | None]


class EntraUser(EntraBase):
    __tablename__ = "entra_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "object_id"),
        UniqueConstraint("tenant_id", "local_employee_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    object_id: Mapped[str] = mapped_column(String(36))
    display_name: Mapped[str | None] = mapped_column(String(256))
    principal_name: Mapped[str | None] = mapped_column(String(320))
    mail: Mapped[str | None] = mapped_column(String(320))
    user_type: Mapped[str | None] = mapped_column(String(32))
    employee_type: Mapped[str | None] = mapped_column(String(120))
    employee_number: Mapped[str | None] = mapped_column(String(64))
    given_name: Mapped[str | None] = mapped_column(String(100))
    surname: Mapped[str | None] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(120))
    account_enabled: Mapped[bool | None] = mapped_column(Boolean)
    present: Mapped[bool] = mapped_column(Boolean)
    last_seen_run_id: Mapped[int] = mapped_column(ForeignKey("entra_sync_runs.id"))
    local_employee_id: Mapped[int | None] = mapped_column(ForeignKey(Employee.id))


class EntraGroup(EntraBase):
    __tablename__ = "entra_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "object_id"),
        UniqueConstraint("tenant_id", "local_group_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    object_id: Mapped[str] = mapped_column(String(36))
    display_name: Mapped[str | None] = mapped_column(String(256))
    security_enabled: Mapped[bool | None] = mapped_column(Boolean)
    present: Mapped[bool] = mapped_column(Boolean)
    last_seen_run_id: Mapped[int] = mapped_column(ForeignKey("entra_sync_runs.id"))
    local_group_id: Mapped[int | None] = mapped_column(ForeignKey(Group.id))


class EntraMembership(EntraBase):
    __tablename__ = "entra_memberships"

    group_id: Mapped[int] = mapped_column(ForeignKey("entra_groups.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("entra_users.id"), primary_key=True)
