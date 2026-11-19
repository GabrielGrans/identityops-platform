from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Column, Integer, MetaData, Table, select

from backend.app.models.associations import employee_groups, group_permissions
from backend.app.models.employee import Employee
from backend.app.models.entra import EntraGroup, EntraMembership, EntraSyncRun, EntraUser
from backend.app.models.governance import AccessReview
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.services.provisioning_service import snapshot_is_recent

policy_table = Table(
    "enterprise_governance_policy", MetaData(),
    Column("id", Integer, primary_key=True), Column("rules", JSON, nullable=False),
)


def latest_snapshot(db, tenant):
    return db.scalar(select(EntraSyncRun).where(
        EntraSyncRun.tenant_id == tenant, EntraSyncRun.status == "completed",
    ).order_by(EntraSyncRun.id.desc()).limit(1))


def snapshot_groups(tenant, run_id):
    return select(EntraGroup).where(
        EntraGroup.tenant_id == tenant, EntraGroup.present.is_(True),
        EntraGroup.last_seen_run_id == run_id,
    )


def access_comparison(db, tenant, run_id, user, external_groups):
    if user.local_employee_id is None or not user.present or user.last_seen_run_id != run_id:
        return None
    mapped = {
        group.local_group_id: group for group in db.scalars(
            snapshot_groups(tenant, run_id).where(EntraGroup.local_group_id.is_not(None))
        )
    }
    local = set(db.scalars(select(Group.id).join(employee_groups).where(
        employee_groups.c.employee_id == user.local_employee_id, Group.is_active.is_(True),
    )))
    external = {group.local_group_id for group in external_groups if group.local_group_id in mapped}
    return {
        "local_only_group_ids": sorted((local & mapped.keys()) - external),
        "entra_only_group_ids": sorted(external - local),
        "unmapped_local_group_ids": sorted(local - mapped.keys()),
        "unmapped_entra_group_ids": sorted(group.object_id for group in external_groups if group.local_group_id is None),
    }


def evaluate(db, policy, tenant, include_entra):
    findings = []

    def append(rule, employee_id, **evidence):
        findings.append({"rule": rule, "employee_id": employee_id, "evidence": evidence})

    local_groups = defaultdict(set)
    inactive = set()
    for employee_id, status, group_id in db.execute(
        select(Employee.id, Employee.status, Group.id).select_from(Employee).join(employee_groups).join(Group).where(Group.is_active.is_(True))
    ):
        local_groups[employee_id].add(group_id)
        if status == "inactive":
            inactive.add(employee_id)
    grants = defaultdict(set)
    for group_id, code in db.execute(select(group_permissions.c.group_id, Permission.code)
        .join(Permission).where(Permission.is_active.is_(True))):
        grants[group_id].add(code)
    for employee_id, groups in local_groups.items():
        if employee_id in inactive:
            append("inactive_access", employee_id, group_ids=sorted(groups))
            continue
        effective = set().union(*(grants[group] for group in groups))
        if policy.max_permissions is not None and len(effective) > policy.max_permissions:
            append("excessive_permissions", employee_id, count=len(effective), limit=policy.max_permissions)
        for grant in policy.privileged_groups:
            if grant.group_id in groups and employee_id not in grant.allowed_employee_ids:
                append("privileged_access", employee_id, group_id=grant.group_id)
        for pair in policy.conflicts:
            if set(pair) <= effective:
                append("segregation_of_duties", employee_id, permission_codes=list(pair))

    cutoff = datetime.now(timezone.utc) - timedelta(days=policy.review_max_age_days)
    for employee_id, review_id, group_id, created_at in db.execute(
        select(AccessReview.employee_id, AccessReview.id, AccessReview.group_id, AccessReview.created_at)
        .where(AccessReview.status == "pending", AccessReview.created_at < cutoff)
    ):
        append("overdue_review", employee_id, review_id=review_id, group_id=group_id,
               opened_at=created_at.isoformat(), max_age_days=policy.review_max_age_days)

    entra_state = "unavailable"
    if include_entra and tenant and (snapshot := latest_snapshot(db, tenant)) and snapshot_is_recent(snapshot):
        entra_state = "evaluated"
        mapping = {
            group.id: group.local_group_id for group in db.scalars(
                snapshot_groups(tenant, snapshot.id).where(EntraGroup.local_group_id.is_not(None))
            )
        }
        linked = {
            user_id: employee_id for user_id, employee_id in db.execute(
                select(EntraUser.id, EntraUser.local_employee_id).where(
                    EntraUser.tenant_id == tenant, EntraUser.present.is_(True),
                    EntraUser.last_seen_run_id == snapshot.id, EntraUser.local_employee_id.is_not(None),
                )
            )
        }
        external = defaultdict(set)
        for user_id, group_id in db.execute(select(EntraMembership.user_id, EntraMembership.group_id)
            .join(EntraUser).where(EntraUser.tenant_id == tenant, EntraUser.last_seen_run_id == snapshot.id)):
            if user_id in linked and group_id in mapping:
                external[user_id].add(mapping[group_id])
        mapped_ids = set(mapping.values())
        for user_id, employee_id in linked.items():
            local = local_groups[employee_id] & mapped_ids
            only_local = sorted(local - external[user_id])
            only_entra = sorted(external[user_id] - local)
            if only_local or only_entra:
                append("entra_mismatch", employee_id, local_only_group_ids=only_local,
                       entra_only_group_ids=only_entra, snapshot_id=snapshot.id)
    return sorted(findings, key=lambda row: (row["rule"], row["employee_id"], repr(row["evidence"]))), entra_state
