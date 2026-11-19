from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, inspect, not_, or_, select, tuple_
from sqlalchemy.orm import Session

from backend.app.models.associations import employee_groups, group_permissions
from backend.app.models.certification import CertificationCampaign, CertificationItem
from backend.app.models.department import Department
from backend.app.models.employee import Employee
from backend.app.models.governance import AccessRequest, AccessReview, AuditEvent
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.schemas.dashboard import ActivityEvent, ActivityPage, ActivityCategory, DashboardSummary


DASHBOARD_PERMISSIONS = {
    "employees:read", "departments:read", "groups:read", "permissions:read",
    "access:manage", "reviews:manage", "certifications:manage", "audit:read",
}
PRIVILEGED_CODES = {
    "access:manage", "groups:manage", "permissions:manage", "departments:manage",
    "employees:create", "employees:update", "employees:deactivate", "reviews:manage",
    "certifications:manage", "certifications:review", "entra:manage_links",
}
REVOCATIONS = ("employee.group.removed", "review.revoked", "certification.item_revoked")
FAILURE = "entra.sync.failed"
LIFECYCLE = ("lifecycle.joiner", "lifecycle.mover", "lifecycle.leaver")

PREFIXES = {
    "lifecycle": ("lifecycle.",),
    "access": ("employee.group.", "request.", "review.", "group.permission.", "group.requestable."),
    "certification": ("certification.",),
    "entra": ("entra.",),
}
LABELS = {
    "auth.login": "Local sign-in",
    "lifecycle.joiner": "Joiner completed",
    "lifecycle.mover": "Mover completed",
    "lifecycle.leaver": "Leaver completed",
    "employee.group.assigned": "Group membership granted",
    "employee.group.removed": "Group membership removed",
    "request.submitted": "Access requested",
    "request.approved": "Access approved",
    "request.rejected": "Access rejected",
    "review.opened": "Access review opened",
    "review.retained": "Access retained in review",
    "review.revoked": "Access revoked in review",
    "group.permission.assigned": "Group permission assigned",
    "group.permission.removed": "Group permission removed",
    "group.requestable.enabled": "Group opened to requests",
    "group.requestable.disabled": "Group closed to requests",
    "certification.created": "Certification campaign created",
    "certification.activated": "Certification campaign activated",
    "certification.completed": "Certification campaign completed",
    "certification.cancelled": "Certification campaign cancelled",
    "certification.expired": "Certification campaign expired",
    "certification.reviewers_changed": "Certification reviewers updated",
    "certification.item_retained": "Access retained in certification",
    "certification.item_revoked": "Access revoked in certification",
    "certification.item_superseded": "Certification item superseded",
    "entra.sync.started": "Entra synchronization started",
    "entra.sync.completed": "Entra synchronization completed",
    "entra.sync.failed": "Entra synchronization failed",
    "entra.provision.created": "Local employee imported from Entra",
    "entra.provision.linked": "Local employee linked to Entra",
    "entra.provision.rejected": "Local reconciliation batch rejected",
    "entra.provision.failed": "Local reconciliation batch failed",
    "entra.link.created": "Entra mapping created",
    "entra.link.removed": "Entra mapping removed",
    "employee.create": "Employee created",
    "employee.update": "Employee updated",
    "employee.activate": "Employee activated",
    "employee.password.set": "Employee password set",
    "employee.password.reset": "Employee password reset",
    "employee.deactivate": "Employee deactivated",
    "department.create": "Department created",
    "department.update": "Department updated",
    "department.deactivate": "Department deactivated",
    "permission.create": "Permission created",
    "permission.update": "Permission updated",
    "permission.deactivate": "Permission deactivated",
    "group.create": "Group created",
    "group.update": "Group updated",
    "group.deactivate": "Group deactivated",
    "system.admin.bootstrapped": "Administrator initialized",
    "system.password.configured": "Local credentials configured",
    "system.permissions.seeded": "Default permissions seeded",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def count_states(db, model, condition):
    active, inactive = db.execute(
        select(func.count().filter(condition), func.count().filter(~condition)).select_from(model)
    ).one()
    return {"active": active, "inactive": inactive}


def decisions(db, model, timestamp, start, end):
    retained, revoked = db.execute(
        select(
            func.count().filter(model.status == "retained"),
            func.count().filter(model.status == "revoked"),
        ).where(timestamp >= start, timestamp <= end, model.status.in_(("retained", "revoked")))
    ).one()
    return {"retained": retained, "revoked": revoked}


def certifications(db: Session, start: datetime, end: datetime):
    active = CertificationCampaign.status == "active"
    overdue = CertificationCampaign.due_on < end.date()
    pending = CertificationItem.status == "pending"
    active_campaigns, overdue_campaigns = db.execute(
        select(func.count(), func.count().filter(overdue)).where(active)
    ).one()
    pending_items, retained, revoked, superseded, overdue_items = db.execute(
        select(
            func.count().filter(pending),
            func.count().filter(CertificationItem.status == "retained"),
            func.count().filter(CertificationItem.status == "revoked"),
            func.count().filter(CertificationItem.status == "superseded"),
            func.count().filter(pending & overdue),
        ).select_from(CertificationItem)
        .join(CertificationCampaign, CertificationCampaign.id == CertificationItem.campaign_id).where(active)
    ).one()
    return {
        "active_campaigns": active_campaigns,
        "overdue_campaigns": overdue_campaigns,
        "overdue_items": overdue_items,
        "pending": pending_items,
        "retained": retained,
        "revoked": revoked,
        "superseded": superseded,
        "decisions": decisions(db, CertificationItem, CertificationItem.decided_at, start, end),
    }


def security_snapshot(db: Session):
    privileged_group = (
        select(1)
        .select_from(group_permissions)
        .join(Permission, Permission.id == group_permissions.c.permission_id)
        .where(group_permissions.c.group_id == employee_groups.c.group_id,
               Permission.is_active.is_(True), Permission.code.in_(PRIVILEGED_CODES))
        .exists()
    )
    privileged, inactive = db.execute(
        select(
            func.count().filter((Employee.status == "active") & privileged_group),
            func.count(distinct(Employee.id)).filter(Employee.status == "inactive"),
        )
        .select_from(employee_groups)
        .join(Employee, Employee.id == employee_groups.c.employee_id)
        .join(Group, Group.id == employee_groups.c.group_id)
        .where(Group.is_active.is_(True))
    ).one()
    return {"privileged_memberships": privileged, "inactive_accounts_with_active_groups": inactive}


def activity_counts(db: Session, start: datetime, end: datetime):
    action = AuditEvent.action
    joiners, movers, leavers, revocations, failures = db.execute(
        select(
            *(func.count().filter(action == value) for value in LIFECYCLE),
            func.count().filter(action.in_(REVOCATIONS)),
            func.count().filter(action == FAILURE),
        ).where(AuditEvent.created_at >= start, AuditEvent.created_at <= end,
                action.in_((*LIFECYCLE, *REVOCATIONS, FAILURE)))
    ).one()
    return dict(joiners=joiners, movers=movers, leavers=leavers, revocation_events=revocations, failed_entra_syncs=failures)


def summary(db: Session, permissions: set[str], days: int) -> DashboardSummary:
    end = utcnow()
    start = end - timedelta(days=days)
    panels = {}
    for code, name, model, condition in (
        ("employees:read", "employees", Employee, Employee.status == "active"),
        ("departments:read", "departments", Department, Department.is_active.is_(True)),
        ("groups:read", "groups", Group, Group.is_active.is_(True)),
        ("permissions:read", "permissions", Permission, Permission.is_active.is_(True)),
    ):
        if code in permissions:
            panels[name] = count_states(db, model, condition)
    if "access:manage" in permissions:
        panels["pending_requests"] = db.scalar(select(func.count()).where(AccessRequest.status == "pending"))
        panels["security"] = security_snapshot(db)
    if "reviews:manage" in permissions:
        panels["reviews"] = {
            "pending": db.scalar(select(func.count()).where(AccessReview.status == "pending")),
            "decisions": decisions(db, AccessReview, AccessReview.decided_at, start, end),
        }
    if "certifications:manage" in permissions:
        inspector = inspect(db.connection())
        available = all(inspector.has_table(table) for table in ("certification_campaigns", "certification_items"))
        panels["certification_available"] = available
        if available:
            panels["certification"] = certifications(db, start, end)
    if "audit:read" in permissions:
        panels["activity"] = activity_counts(db, start, end)
    return DashboardSummary(as_of=end, period_start=start, **panels)


def activity_category(action: str) -> ActivityCategory:
    for category, prefixes in PREFIXES.items():
        if action.lower().startswith(prefixes):
            return category
    return "other"


def activity_page(
    db: Session, days: int, limit: int, before_id: int | None, category: ActivityCategory | None,
) -> ActivityPage:
    end = utcnow()
    start = end - timedelta(days=days)
    filters = [AuditEvent.created_at >= start, AuditEvent.created_at <= end]
    if category:
        prefixes = PREFIXES.get(category, tuple(prefix for values in PREFIXES.values() for prefix in values))
        match = or_(*(func.lower(AuditEvent.action).startswith(prefix, autoescape=True) for prefix in prefixes))
        filters.append(not_(match) if category == "other" else match)
    if before_id is not None:
        cursor = db.execute(select(AuditEvent.created_at, AuditEvent.id).where(AuditEvent.id == before_id)).first()
        if cursor is None:
            return ActivityPage(items=[], next_before_id=None)
        filters.append(tuple_(AuditEvent.created_at, AuditEvent.id) < tuple_(cursor.created_at, cursor.id))

    rows = db.execute(
        select(AuditEvent.id, AuditEvent.created_at, AuditEvent.action)
        .where(*filters).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
    ).all()
    items = [
        ActivityEvent(id=id, created_at=created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None
                      else created_at.astimezone(timezone.utc),
                      category=activity_category(action), label=LABELS.get(action, "Audit event"))
        for id, created_at, action in rows[:limit]
    ]
    return ActivityPage(items=items, next_before_id=items[-1].id if len(rows) > limit else None)
