from collections import Counter
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, inspect, select, true

from backend.app.api.routes.entra import Config, DB
from backend.app.api.routes.governance import Actor
from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.models.certification import CertificationCampaign, CertificationItem
from backend.app.models.department import Department
from backend.app.models.employee import Employee
from backend.app.models.entra import EntraGroup, EntraSyncRun, EntraUser
from backend.app.models.governance import AccessRequest, AuditEvent
from backend.app.models.group import Group
from backend.app.services.department_catalog import OFFICIAL, department_key, official_code
from backend.app.services.entra_automation_tables import alerts, changes, policies, state
from backend.app.services.entra_service import utcnow
from backend.app.services.enterprise_governance import latest_snapshot
from backend.app.services.provisioning_service import snapshot_is_recent

router = APIRouter(tags=["IAM operations"])


def grouped_counts(db, column, *conditions):
    return dict(db.execute(select(column, func.count()).where(*conditions).group_by(column)).all())


def certification_metrics(db):
    now = utcnow().date()
    campaign_count = db.scalar(select(func.count()).select_from(CertificationCampaign))
    status = CertificationItem.status
    retained, revoked, pending, overdue = db.execute(select(
        func.count().filter(status == "retained"), func.count().filter(status == "revoked"),
        func.count().filter((status == "pending") & (CertificationCampaign.status == "active")),
        func.count().filter((status == "pending") & (CertificationCampaign.status == "active") &
                            (CertificationCampaign.due_on < now)),
    ).select_from(CertificationItem).join(CertificationCampaign,
                                         CertificationCampaign.id == CertificationItem.campaign_id)).one()
    completed = retained + revoked
    total = completed + pending
    return {"campaigns": campaign_count, "decisions": completed, "completed": completed,
            "pending": pending, "revoked": revoked, "overdue": overdue,
            "completion": round(completed * 100 / total) if total else None}


@router.get("/v1/dashboard/operations")
def dashboard_operations(db: DB, config: Config, actor: Actor):
    permissions = set(db.scalars(effective_permissions(actor.id)))
    relevant = {"employees:read", "groups:read", "departments:read", "entra:read", "governance:read",
                "access:manage", "entra:approve_change", "certifications:manage"}
    if not permissions & relevant:
        raise HTTPException(403, "Dashboard permission required")
    tables = set(inspect(db.connection()).get_table_names())
    result = {}
    tenant = config.entra_tenant
    if "employees:read" in permissions:
        result["local_employees"] = db.scalar(select(func.count()).select_from(Employee))
        result["local_unassigned"] = db.scalar(select(func.count()).select_from(Employee).where(Employee.department_id.is_(None)))
    if "groups:read" in permissions:
        result["local_groups"] = db.scalar(select(func.count()).select_from(Group))
    if "departments:read" in permissions:
        result["official_departments"] = len({code for department in db.scalars(select(Department).where(Department.is_active.is_(True)))
                                              if (code := official_code(department.name, department.code))})
    if "entra:read" in permissions:
        result["entra"] = {"health": "unavailable" if config.ENTRA_ENABLED else "disabled", "last_success": None}
        if tenant and {"entra_sync_runs", "entra_users", "entra_groups"} <= tables:
            snapshot = latest_snapshot(db, tenant)
            last = db.scalar(select(EntraSyncRun).where(EntraSyncRun.tenant_id == tenant)
                             .order_by(EntraSyncRun.id.desc()).limit(1))
            sync_state = db.scalar(select(state.c.failures).where(state.c.tenant == tenant)) if state.name in tables else None
            if not snapshot and (last or sync_state):
                result["entra"]["health"] = "failed" if sync_state or last.status == "failed" else last.status
            if snapshot:
                health = ("failed" if last.status == "failed" or sync_state else
                          "running" if last.status == "running" else
                          "synchronized" if snapshot_is_recent(snapshot) else "stale")
                result["entra"] = {
                    "health": health, "last_success": snapshot.finished_at,
                    "stale": not snapshot_is_recent(snapshot),
                    "users": db.scalar(select(func.count()).select_from(EntraUser).where(
                        EntraUser.tenant_id == tenant, EntraUser.present.is_(True))),
                    "groups": db.scalar(select(func.count()).select_from(EntraGroup).where(
                        EntraGroup.tenant_id == tenant, EntraGroup.present.is_(True), EntraGroup.security_enabled.is_(True))),
                }
                result["entra"]["identity_status"] = {
                    "active": 0, "disabled": 0, "unknown": 0,
                }
                for enabled, count in grouped_counts(
                    db, EntraUser.account_enabled, EntraUser.tenant_id == tenant,
                    EntraUser.present.is_(True),
                ).items():
                    label = {True: "active", False: "disabled", None: "unknown"}[enabled]
                    result["entra"]["identity_status"][label] = count
                if "department" in {column["name"] for column in inspect(db.connection()).get_columns("entra_users")}:
                    result["entra"]["unassigned"] = sum(
                        count for label, count in grouped_counts(db, EntraUser.department,
                            EntraUser.tenant_id == tenant, EntraUser.present.is_(True)).items() if not department_key(label)
                    )
    if "access:manage" in permissions:
        result["pending_local"] = db.scalar(select(func.count()).select_from(AccessRequest).where(AccessRequest.status == "pending"))
    if tenant and "entra:approve_change" in permissions and changes.name in tables:
        counts = grouped_counts(db, changes.c.status, changes.c.tenant == tenant)
        open_counts = grouped_counts(db, changes.c.status, changes.c.tenant == tenant, changes.c.expires_at > utcnow())
        result["pending_entra"] = open_counts.get("pending", 0)
        result["provisioning_active"] = sum(open_counts.get(key, 0) for key in ("approved", "direct_authorized", "executing"))
        result["provisioning_failed"] = counts.get("failed", 0) + counts.get("conflict", 0)
    if tenant and {"governance:read", "entra:read"} <= permissions and alerts.name in tables:
        severity = alerts.c.payload["severity"].as_string()
        result["findings"] = grouped_counts(db, severity, alerts.c.tenant == tenant, alerts.c.state != "resolved")
    if "certifications:manage" in permissions and {"certification_campaigns", "certification_items"} <= tables:
        result["certification"] = certification_metrics(db)
    return result


@router.get("/v1/dashboard/access-activity")
def access_activity(db: DB, config: Config, actor: Actor, days: Literal["7", "30", "90"] = "30"):
    permissions = set(db.scalars(effective_permissions(actor.id)))
    if "entra:approve_change" not in permissions:
        raise HTTPException(403, "Dashboard permission required")
    tenant = config.entra_tenant
    if not tenant or not inspect(db.connection()).has_table(changes.name):
        return {"available": False}

    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=int(days) - 1)
    month = today.replace(day=1)
    terminal = ("succeeded", "failed", "conflict")
    completed_at = func.min(AuditEvent.created_at).label("completed_at")
    outcomes = (
        select(changes.c.id, changes.c.status, changes.c.group_object_id,
               changes.c.request["add"].as_boolean().label("added"),
               changes.c.request["expected"].as_boolean().label("previously_present"),
               completed_at)
        .join(AuditEvent, (AuditEvent.target_id == changes.c.id)
              & (AuditEvent.target_type == changes.name)
              & (AuditEvent.action == ("entra.provisioning." + changes.c.status))
              & (AuditEvent.details["tenant_id"].as_string() == tenant))
        .where(changes.c.tenant == tenant, changes.c.status.in_(terminal),
               (changes.c.status != "succeeded") | (AuditEvent.details["verified_membership"].as_boolean()
                                                    == changes.c.request["add"].as_boolean()))
        .group_by(changes.c.id)
        .subquery()
    )
    # A verified no-op is a successful execution, but not a grant or revocation.
    changed = (outcomes.c.status == "succeeded") & (outcomes.c.added != outcomes.c.previously_present)
    grant = changed & outcomes.c.added.is_(True)
    revoke = changed & outcomes.c.added.is_(False)
    grants, revocations = db.execute(select(func.count().filter(grant), func.count().filter(revoke))
                                    .where(outcomes.c.completed_at.between(month, now))).one()
    timestamp = outcomes.c.completed_at
    if db.get_bind().dialect.name == "postgresql":
        timestamp = func.timezone("UTC", timestamp)
    day = func.date(timestamp)
    counts = {row[0]: row[1:] for row in db.execute(
        select(day, func.count().filter(grant), func.count().filter(revoke),
               func.count().filter(outcomes.c.status == "succeeded"),
               func.count().filter(outcomes.c.status.in_(("failed", "conflict"))))
        .where(outcomes.c.completed_at.between(start, now)).group_by(day)
    )}
    series = []
    for offset in range(int(days)):
        date = (start + timedelta(days=offset)).date()
        added, removed, succeeded, failed = counts.get(date, (0, 0, 0, 0))
        series.append({"date": date, "grants": added, "revocations": removed,
                       "succeeded": succeeded, "failed": failed})

    group_count = func.count().label("count")
    groups = db.execute(select(outcomes.c.group_object_id, func.max(EntraGroup.display_name), group_count)
        .outerjoin(EntraGroup, (EntraGroup.tenant_id == tenant)
                   & (EntraGroup.object_id == outcomes.c.group_object_id))
        .where(changed, outcomes.c.completed_at.between(start, now)).group_by(outcomes.c.group_object_id)
        .order_by(group_count.desc(), outcomes.c.group_object_id).limit(10)).all()
    return {"available": True, "month": {"grants": grants, "revocations": revocations}, "series": series,
            "groups": [{"id": key, "name": name, "count": count} for key, name, count in groups]}


@router.get("/v1/dashboard/membership-observations")
def membership_observations(db: DB, config: Config, actor: Actor, days: Literal["7", "30", "90"] = "30"):
    permissions = set(db.scalars(effective_permissions(actor.id)))
    if not {"audit:read", "entra:read"} <= permissions:
        raise HTTPException(403, "Dashboard permission required")
    tenant = config.entra_tenant
    if not tenant or not inspect(db.connection()).has_table(EntraSyncRun.__tablename__):
        return {"available": False}
    latest = latest_snapshot(db, tenant)
    if latest is None:
        return {"available": False}

    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=int(days) - 1)
    month = today.replace(day=1)
    added, removed = "entra.membership.added", "entra.membership.removed"
    scope = (
        AuditEvent.action.in_((added, removed)),
        AuditEvent.details["tenant_id"].as_string() == tenant,
    )
    timestamp = AuditEvent.created_at
    if db.get_bind().dialect.name == "postgresql":
        timestamp = func.timezone("UTC", timestamp)
    day = func.date(timestamp)
    grant = AuditEvent.action == added
    revoke = AuditEvent.action == removed
    grants, revocations = db.execute(
        select(func.count().filter(grant), func.count().filter(revoke))
        .where(*scope, AuditEvent.created_at >= month)
    ).one()
    counts = {str(date): (grants, revocations) for date, grants, revocations in db.execute(
        select(day, func.count().filter(grant), func.count().filter(revoke))
        .where(*scope, AuditEvent.created_at >= start).group_by(day)
    )}
    series = []
    for offset in range(int(days)):
        date = (start + timedelta(days=offset)).date().isoformat()
        daily_grants, daily_revocations = counts.get(date, (0, 0))
        series.append({"date": date, "grants": daily_grants, "revocations": daily_revocations})

    group_id = AuditEvent.details["group_object_id"].as_string()
    group_name = AuditEvent.details["group_name"].as_string()
    group_count = func.count().label("count")
    groups = db.execute(
        select(group_id, func.max(group_name), group_count)
        .where(*scope, AuditEvent.created_at >= start).group_by(group_id)
        .order_by(group_count.desc(), group_id).limit(10)
    ).all()
    recent = db.scalars(
        select(AuditEvent).where(*scope, AuditEvent.created_at >= start)
        .order_by(AuditEvent.id.desc()).limit(25)
    )
    return {
        "available": True, "month": {"grants": grants, "revocations": revocations}, "series": series,
        "groups": [{"id": key, "name": name, "count": count} for key, name, count in groups],
        "recent": [
            {"id": row.id, "observed_at": row.created_at, "operation": "added" if row.action == added else "removed",
             "user_name": row.details["user_name"], "user_object_id": row.details["user_object_id"],
             "group_name": row.details["group_name"], "group_object_id": row.details["group_object_id"]}
            for row in recent
        ],
    }


@router.get("/v1/dashboard/risk-distribution")
def risk_distribution(db: DB, config: Config, actor: Actor):
    permissions = set(db.scalars(effective_permissions(actor.id)))
    if not {"governance:read", "entra:read"} <= permissions:
        raise HTTPException(403, "Dashboard permission required")
    tenant = config.entra_tenant
    if not tenant or not inspect(db.connection()).has_table(alerts.name):
        return {"available": False}

    rule = alerts.c.payload["rule"].as_string()
    scope = (alerts.c.tenant == tenant, alerts.c.state != "resolved")
    counts = grouped_counts(db, rule, *scope)
    departments = None
    if "departments:read" in permissions:
        # Prefer the directory attribute, then the linked employee department.
        name = func.coalesce(func.nullif(func.trim(EntraUser.department), ""), Department.name)
        department_key_sql = func.lower(name)
        display = func.min(name)
        count = func.count().label("count")
        rows = db.execute(select(display, count).select_from(alerts)
            .outerjoin(EntraUser, (EntraUser.tenant_id == tenant)
                       & (EntraUser.object_id == alerts.c.payload["identity"].as_string()))
            .outerjoin(Employee, Employee.id == func.coalesce(EntraUser.local_employee_id, alerts.c.payload["employee_id"].as_integer()))
            .outerjoin(Department, Department.id == Employee.department_id)
            .where(*scope).group_by(department_key_sql).order_by(count.desc(), department_key_sql).limit(10)).all()
        departments = [{"name": label, "count": count} for label, count in rows]
    policy_findings = sum(counts.get(key, 0) for key in
                          ("unexpected_access", "missing_access", "privileged_access", "segregation_of_duties"))
    if db.get_bind().dialect.name == "postgresql":
        groups = func.json_array_elements_text(alerts.c.payload["group_ids"]).table_valued(
            "group_id", joins_implicitly=True,
        ).render_derived()
    else:
        groups = func.json_each(alerts.c.payload["group_ids"]).table_valued("value", joins_implicitly=True)
    group_id = groups.c.group_id if db.get_bind().dialect.name == "postgresql" else groups.c.value
    violating = select(alerts.c.payload["identity"].as_string().label("identity"), group_id).select_from(
        alerts.join(groups, true())
    ).where(*scope, rule.in_(("unexpected_access", "privileged_access", "segregation_of_duties"))).distinct()
    memberships = db.scalar(select(func.count()).select_from(violating.subquery()))
    return {"available": True, "departments": departments, "policy_findings": policy_findings,
            "violating_memberships": memberships}


@router.get("/departments/operations/catalog", dependencies=[Depends(require_permission("departments:read"))])
def department_operations(db: DB, config: Config, actor: Actor):
    permissions = set(db.scalars(effective_permissions(actor.id)))
    tables = set(inspect(db.connection()).get_table_names())
    catalog = dict(OFFICIAL)
    local_counts = grouped_counts(db, Employee.department_id)
    tenant = config.entra_tenant
    roles = []
    if tenant and {"governance:read", "entra:read"} <= permissions and policies.name in tables:
        data = db.scalar(select(policies.c.rules).where(policies.c.tenant == tenant)) or {}
        roles = data.get("roles", [])
    local = []
    for row in db.scalars(select(Department).order_by(Department.name, Department.id)):
        code = official_code(row.name, row.code)
        local.append({"id": row.id, "name": row.name, "official": catalog.get(code), "active": row.is_active,
                      "employees": local_counts.get(row.id, 0) if "employees:read" in permissions else None,
                      "policies": [role["name"] for role in roles if role.get("department_id") == row.id]})
    grouped = Counter()
    names = {}
    if tenant and "entra:read" in permissions and "entra_users" in tables:
        if "department" in {column["name"] for column in inspect(db.connection()).get_columns("entra_users")}:
            for label, count in grouped_counts(db, EntraUser.department,
                EntraUser.tenant_id == tenant, EntraUser.present.is_(True)).items():
                key = department_key(label)
                grouped[key] += count
                names.setdefault(key, (label or "").strip())
    entra = []
    for key, count in sorted(grouped.items()):
        code = official_code(key)
        entra.append({"key": key, "name": catalog.get(code) or names[key] or None, "official": catalog.get(code),
                      "employees": count, "policies": [role["name"] for role in roles
                          if role.get("entra_department") and department_key(role["entra_department"]) == key]})
    return {"local": local, "entra": entra}
