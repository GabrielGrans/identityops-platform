"""Tenant checkpoint processing. A failed read cannot replace a published snapshot."""
from datetime import timedelta

from sqlalchemy import select

from backend.app.models.entra import EntraGroup, EntraUser
from backend.app.services.entra_automation_tables import state
from backend.app.services.entra_service import synchronize, utcnow
from backend.app.services.enterprise_governance import latest_snapshot
from backend.app.services.graph_client import (
    DirectorySnapshot, GraphError, MAX_OBJECTS, object_id, optional_bool, optional_text,
)

USER_FIELDS = {
    "displayName": ("display_name", 256), "userPrincipalName": ("principal_name", 320),
    "mail": ("mail", 320), "userType": ("user_type", 32), "employeeType": ("employee_type", 120),
    "employeeId": ("employee_number", 64), "givenName": ("given_name", 100),
    "surname": ("surname", 100), "jobTitle": ("job_title", 120), "accountEnabled": ("account_enabled", None),
}
GROUP_FIELDS = {"displayName": ("display_name", 256), "securityEnabled": ("security_enabled", None)}


def materialize(db, model, tenant, fields, patches, incremental):
    rows = {}
    if incremental:
        for row in db.scalars(select(model).where(model.tenant_id == tenant, model.present.is_(True))):
            rows[row.object_id] = {"object_id": row.object_id, **{name: getattr(row, name) for name, _ in fields.values()}}
    for patch in patches:
        key = object_id(patch)
        if "@removed" in patch:
            rows.pop(key, None)
            continue
        row = rows.setdefault(key, {"object_id": key, **{name: None for name, _ in fields.values()}})
        for source, (name, limit) in fields.items():
            if source in patch:
                row[name] = optional_bool(patch, source) if limit is None else optional_text(patch, source, limit)
    if len(rows) > MAX_OBJECTS:
        raise GraphError("sync_limit")
    return rows


def sync_due(db, tenant, interval, make_client):
    current = db.execute(select(state).where(state.c.tenant == tenant)).mappings().one_or_none()
    now = utcnow()
    if current and current.next_run > now:
        return
    checkpoint = current.checkpoint if current else {}
    latest = latest_snapshot(db, tenant)
    use_delta = bool(latest and checkpoint.get("run_id") == latest.id and
                     checkpoint.get("full_after", "") > now.isoformat())
    next_checkpoint = {}

    def fetch():
        graph = make_client()
        base = latest_snapshot(db, tenant)
        incremental = bool(use_delta and base and base.id == checkpoint.get("run_id"))
        try:
            users, user_link = graph.delta("users", "id," + ",".join(USER_FIELDS), checkpoint.get("users") if incremental else None)
            groups, group_link = graph.delta("groups", "id," + ",".join(GROUP_FIELDS), checkpoint.get("groups") if incremental else None)
        except GraphError as error:
            if error.code != "delta_expired" or not incremental:
                raise
            incremental = False
            users, user_link = graph.delta("users", "id," + ",".join(USER_FIELDS))
            groups, group_link = graph.delta("groups", "id," + ",".join(GROUP_FIELDS))
        users = materialize(db, EntraUser, tenant, USER_FIELDS, users, incremental)
        groups = materialize(db, EntraGroup, tenant, GROUP_FIELDS, groups, incremental)
        security_groups = {key for key, row in groups.items() if row["security_enabled"] is True}
        edges, skipped = graph.direct_memberships(security_groups, users)
        next_checkpoint.update(users=user_link, groups=group_link,
                               full_after=checkpoint["full_after"] if incremental else (now + timedelta(days=1)).isoformat())
        return DirectorySnapshot(users, groups, edges, skipped)

    def save(values):
        where = state.c.tenant == tenant
        if current is None:
            db.execute(state.insert().values(tenant=tenant, **values))
        else:
            db.execute(state.update().where(where).values(**values))

    def finish(run):
        next_checkpoint["run_id"] = run.id
        save(dict(checkpoint=next_checkpoint, next_run=utcnow() + timedelta(minutes=interval), failures=0))

    try:
        synchronize(db, tenant, None, fetch, before_commit=finish)
    except GraphError as error:
        db.rollback()
        if error.code == "sync_running":
            return
        attempts = current.failures + 1 if current else 1
        retry = max(error.retry_after or 0, 30 * 2 ** min(attempts - 1, 6))
        save(dict(checkpoint=checkpoint, next_run=utcnow() + timedelta(seconds=retry), failures=attempts))
        db.commit()
