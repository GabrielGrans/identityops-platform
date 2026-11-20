from collections import defaultdict
from datetime import date, timedelta
from hashlib import sha256
import json

from sqlalchemy import select

from backend.app.models.employee import Employee
from backend.app.models.entra import EntraGroup, EntraMembership, EntraUser
from backend.app.models.governance import AccessReview
from backend.app.services.entra_automation_tables import alerts, changes, policies
from backend.app.services.entra_service import utcnow
from backend.app.services.enterprise_governance import latest_snapshot
from backend.app.services.provisioning_service import snapshot_is_recent


def refresh_alerts(db, tenant):
    config = db.scalar(select(policies.c.rules).where(policies.c.tenant == tenant)) or {}
    snapshot = latest_snapshot(db, tenant)
    current = {}
    today = utcnow().date()

    def finding(rule, identity, role, evidence, severity, action, employee_id=None, group_ids=None):
        key = sha256(json.dumps([rule, identity, role, evidence], sort_keys=True).encode()).hexdigest()
        current[key] = dict(rule=rule, identity=identity, policy=role, evidence=evidence, severity=severity,
                            recommended_action=action, employee_id=employee_id, group_ids=group_ids or [],
                            user_object_id=identity if group_ids else None)

    has_snapshot = snapshot_is_recent(snapshot)
    if has_snapshot:
        observed = defaultdict(set)
        for user_id, group_id in db.execute(select(EntraMembership.user_id, EntraGroup.object_id)
            .join(EntraGroup).where(EntraGroup.tenant_id == tenant, EntraGroup.last_seen_run_id == snapshot.id,
                                    EntraGroup.present.is_(True))):
            observed[user_id].add(group_id)
        users = db.execute(select(EntraUser, Employee).outerjoin(Employee, Employee.id == EntraUser.local_employee_id)
            .where(EntraUser.tenant_id == tenant, EntraUser.last_seen_run_id == snapshot.id, EntraUser.present.is_(True)))
        privileged = {group for role in config.get("roles", []) for group in role["privileged"]}
        for user, employee in users:
            object_id = user.object_id
            employee_id = employee.id if employee else None
            groups = observed[user.id]
            if groups and (user.account_enabled is False or (employee and employee.status == "inactive")):
                finding("inactive_access", object_id, "directory", sorted(groups), "high", "Review retained access", employee_id, sorted(groups))
            for role in config.get("roles", []):
                if role["job_title"] and role["job_title"].casefold() != (user.job_title or "").casefold():
                    continue
                if role.get("entra_department") and role["entra_department"].casefold() != (user.department or "").casefold():
                    continue
                if role["department_id"] is not None and (not employee or employee.department_id != role["department_id"]):
                    continue
                if role["employment_status"] and (not employee or employee.status != role["employment_status"]):
                    continue
                excepted = {row["group_id"] for row in role["exceptions"]
                            if row["user_id"] == object_id and date.fromisoformat(row["until"]) >= today}
                expired_groups = sorted({row["group_id"] for row in role["exceptions"]
                                         if row["user_id"] == object_id and date.fromisoformat(row["until"]) < today})
                if expired_groups:
                    finding("expired_exception", object_id, role["name"], expired_groups, "medium",
                            "Review expired exception", employee_id, expired_groups)
                approved = set(role["approved"]) | set(role["required"])
                union = groups - excepted
                recommended = "Review role access"
                for rule, evidence, severity in [
                    ("unexpected_access", union - approved, "medium"),
                    ("missing_access", set(role["required"]) - groups - excepted, "medium"),
                    ("privileged_access", (union & privileged) - approved, "high"),
                ]:
                    if evidence:
                        finding(rule, object_id, role["name"], sorted(evidence), severity, recommended, employee_id, sorted(evidence))
                for pair in role["forbidden"]:
                    if set(pair) <= union:
                        finding("segregation_of_duties", object_id, role["name"], sorted(pair), "high", recommended, employee_id, sorted(pair))

    for employee_id, review_id, group_id in db.execute(select(AccessReview.employee_id, AccessReview.id, AccessReview.group_id)
        .where(AccessReview.status == "pending",
               AccessReview.created_at < utcnow() - timedelta(days=config.get("review_days", 30)))):
        finding("overdue_review", str(employee_id), "review_age", [review_id, group_id],
                "medium", "Complete the pending review", employee_id)
    for row in db.execute(select(changes).where(changes.c.tenant == tenant,
        changes.c.status.in_(("failed", "conflict", "expired")))).mappings():
        finding("provisioning_failed", row.request["user_id"], "provisioning", [row.id, row.status],
                "high", "Investigate the provisioning request", row.employee_id, [row.request["group_id"]])

    seen = {row.key: row for row in db.execute(select(alerts).where(alerts.c.tenant == tenant)).mappings()}
    for key, payload in current.items():
        existing = seen.pop(key, None)
        if existing is None:
            db.execute(alerts.insert().values(tenant=tenant, key=key, state="unread", payload=payload))
        elif existing.payload != payload or existing.state == "resolved":
            db.execute(alerts.update().where(alerts.c.tenant == tenant, alerts.c.key == key)
                       .values(payload=payload, state="unread" if existing.state == "resolved" else existing.state))
    for row in seen.values():
        # A stale or unavailable Graph snapshot is not evidence of resolution.
        if row.state != "resolved" and (has_snapshot or row.payload["rule"] in {"overdue_review", "provisioning_failed"}):
            db.execute(alerts.update().where(alerts.c.tenant == tenant, alerts.c.key == row.key).values(state="resolved"))
    db.commit()
