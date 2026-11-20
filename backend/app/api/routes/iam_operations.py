from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, inspect, select

from backend.app.api.routes.entra import Config, DB
from backend.app.api.routes.governance import Actor
from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.models.certification import CertificationCampaign, CertificationItem
from backend.app.models.department import Department
from backend.app.models.employee import Employee
from backend.app.models.entra import EntraGroup, EntraSyncRun, EntraUser
from backend.app.models.governance import AccessRequest
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
        result["entra"] = {"health": "unavailable", "last_success": None}
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
