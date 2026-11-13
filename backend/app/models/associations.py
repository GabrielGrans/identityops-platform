from sqlalchemy import Column, ForeignKey, Table

from backend.app.models.base import Base


employee_groups = Table(
    "employee_groups",
    Base.metadata,
    Column(
        "employee_id",
        ForeignKey("employees.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "group_id",
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


group_permissions = Table(
    "group_permissions",
    Base.metadata,
    Column(
        "group_id",
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
