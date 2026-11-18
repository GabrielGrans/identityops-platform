from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.app.models.employee import Employee
from backend.app.models.group import Group


class CertificationBase(DeclarativeBase):
    """Managed by Alembic rather than the legacy startup bootstrap."""


class CertificationCampaign(CertificationBase):
    __tablename__ = "certification_campaigns"
    __table_args__ = (
        CheckConstraint("starts_on <= due_on", name="ck_certification_campaign_dates"),
        CheckConstraint(
            "status IN ('draft', 'active', 'completed', 'cancelled', 'expired')",
            name="ck_certification_campaign_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey(Employee.id))
    starts_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CertificationReviewer(CertificationBase):
    __tablename__ = "certification_reviewers"
    __table_args__ = (Index("ix_certification_reviewers_employee", "employee_id"),)

    campaign_id: Mapped[int] = mapped_column(ForeignKey("certification_campaigns.id"), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey(Employee.id), primary_key=True)


class CertificationItem(CertificationBase):
    __tablename__ = "certification_items"
    __table_args__ = (
        UniqueConstraint("campaign_id", "employee_id", "group_id", name="uq_certification_membership"),
        Index("ix_certification_item_campaign_status", "campaign_id", "status", "id"),
        Index("ix_certification_item_membership", "employee_id", "group_id", "status"),
        CheckConstraint(
            """(
                status IN ('retained', 'revoked') AND reviewer_id IS NOT NULL
                AND reviewer_id <> employee_id AND decided_at IS NOT NULL
                AND justification IS NOT NULL AND length(trim(justification)) > 0
            ) OR (
                status IN ('pending', 'superseded', 'not_reviewed') AND reviewer_id IS NULL
                AND decided_at IS NULL AND justification IS NULL
            )""",
            name="ck_certification_item_decision",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("certification_campaigns.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey(Employee.id))
    group_id: Mapped[int] = mapped_column(ForeignKey(Group.id))
    status: Mapped[str] = mapped_column(String(16))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey(Employee.id))
    justification: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
