from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from backend.app.core.authorization import can_direct_provision, effective_permissions
from backend.app.models.employee import Employee
from backend.app.models.entra import EntraGroup, EntraMembership, EntraUser
from backend.app.services.audit_service import record_event
from backend.app.services.entra_automation_tables import changes, policies, state
from backend.app.services.entra_service import utcnow
from backend.app.services.enterprise_governance import latest_snapshot, policy_table
from backend.app.services.graph_client import GraphError
from backend.app.services.provisioning_service import snapshot_is_recent

from backend.app.services.servicenow_client import ServiceNowError, fetch_approval, instance


def recheck_servicenow(config, row, actor, permissions):
    trusted = row.request["servicenow"]
    if (not config.SERVICENOW_ENABLED or config.SERVICENOW_SIMULATION
            or actor.id != config.SERVICENOW_REQUESTER_ID or actor.password_hash is not None
            or permissions != {"entra:request_change"}):
        raise GraphError("servicenow_approval_changed")
    try:
        if instance(config) != trusted["instance"]:
            raise GraphError("servicenow_approval_changed")
        approval = fetch_approval(config, trusted["sys_id"])
    except ServiceNowError as error:
        raise GraphError("servicenow_unavailable" if error.status == 502 else "servicenow_approval_changed") from None
    if approval.model_dump(mode="json") | {"instance": trusted["instance"]} != trusted:
        raise GraphError("servicenow_approval_changed")


def configured_group_ids(value):
    return {str(UUID(key.strip())) for key in value.split(",") if key.strip()}


def group_protection(db, config, tenant):
    try:
        protected = configured_group_ids(config.ENTRA_PROTECTED_GROUP_IDS)
    except ValueError:
        protected = None  # Invalid protection configuration fails closed.
    rules = db.scalar(select(policies.c.rules).where(policies.c.tenant == tenant)) or {}
    if protected is not None:
        protected.update(group for role in rules.get("roles", []) for group in role.get("privileged", []))
    local = db.scalar(select(policy_table.c.rules).where(policy_table.c.id == 1)) or {}
    return protected, {group["group_id"] for group in local.get("privileged_groups", [])}


def eligibility(group, protection):
    protected, local_privileged = protection
    if (protected is None or group.role_assignable is True or group.object_id in protected
            or group.local_group_id in local_privileged):
        return "protected"
    if (
        group.management_metadata_complete is not True or group.security_enabled is not True
        or group.mail_enabled is not False or group.role_assignable is not False
        or group.on_premises_sync_enabled is True or group.group_types != []
    ):
        return "unsupported"
    return "eligible"


def write_blocker(config, group_id, *, simulation=False):
    if not simulation and not config.ENTRA_WRITE_ENABLED:
        return "write_disabled"
    try:
        allowed = configured_group_ids(config.ENTRA_WRITE_GROUP_IDS)
    except ValueError:
        allowed = set()
    return None if group_id in allowed else "group_not_allowlisted"


def require_write_policy(config, group_id, *, simulation=False):
    blocker = write_blocker(config, group_id, simulation=simulation)
    if blocker:
        raise GraphError(blocker)


def preview(db, config, tenant, employee_id, group_id, add, user_id=None):
    snapshot = latest_snapshot(db, tenant)
    if not snapshot_is_recent(snapshot):
        raise GraphError("snapshot_not_recent")
    user = db.scalar(select(EntraUser).where(
        EntraUser.object_id == user_id if user_id else EntraUser.local_employee_id == employee_id,
        EntraUser.tenant_id == tenant, EntraUser.present.is_(True), EntraUser.last_seen_run_id == snapshot.id,
    ))
    group = db.scalar(select(EntraGroup).where(EntraGroup.object_id == group_id, EntraGroup.present.is_(True),
        EntraGroup.tenant_id == tenant, EntraGroup.last_seen_run_id == snapshot.id, EntraGroup.security_enabled.is_(True)))
    employee = db.get(Employee, user.local_employee_id) if user and user.local_employee_id else None
    if not user or not group or (employee_id is not None and user.local_employee_id != employee_id):
        raise GraphError("write_unsupported")
    status = eligibility(group, group_protection(db, config, tenant))
    if status != "eligible":
        raise GraphError("group_protected" if status == "protected" else "write_unsupported")
    if add and (user.account_enabled is not True or (employee and employee.status != "active")):
        raise GraphError("write_unsupported")
    member = db.get(EntraMembership, (group.id, user.id)) is not None
    return {"user_id": user.object_id, "employee_id": user.local_employee_id, "group_id": group_id,
            "add": add, "expected": member, "snapshot_id": snapshot.id, "remote_subject": user_id is not None}


def audit(db, row, action, actor=None, **details):
    record_event(db, actor, f"entra.provisioning.{action}", "entra_access_changes", row.id,
                 tenant_id=row.tenant, employee_id=row.employee_id,
                 group_id=row.request["group_id"], user_id=row.request["user_id"], **details)


def execute_due(db, config, tenant, make_client):
    now = utcnow()
    expired = db.execute(select(changes).where(
        changes.c.tenant == tenant, changes.c.expires_at <= now,
        changes.c.status.in_(("pending", "approved", "direct_authorized", "executing")),
    ).with_for_update(skip_locked=True)).mappings().all()
    for item in expired:
        db.execute(changes.update().where(changes.c.id == item.id).values(status="expired"))
        audit(db, item, "expired")
    db.commit()
    if not config.ENTRA_WRITE_ENABLED:
        return
    row = db.execute(select(changes).where(
        changes.c.tenant == tenant, changes.c.status.in_(("approved", "direct_authorized", "executing")),
        changes.c.next_attempt <= now, changes.c.expires_at > now,
    ).order_by(changes.c.id).limit(1).with_for_update(skip_locked=True)).mappings().one_or_none()
    if row is None:
        return
    request = row.request
    attempts = row.attempts + 1

    try:
        direct = request.get("direct_authorization")
        actors = {row.requester_id: "entra:request_change"}
        if direct:
            if direct.get("actor_id") != row.requester_id or row.reviewer_id is not None or not can_direct_provision(db, row.requester_id):
                raise GraphError("write_unsupported")
        else:
            if row.reviewer_id is None or row.reviewer_id == row.requester_id:
                raise GraphError("write_unsupported")
            actors[row.reviewer_id] = "entra:approve_change"
        for actor_id, permission in actors.items():
            employee = db.get(Employee, actor_id)
            permissions = set(db.scalars(effective_permissions(actor_id)))
            if not employee or employee.status != "active" or permission not in permissions:
                raise GraphError("write_unsupported")
            if actor_id == row.requester_id and request.get("servicenow"):
                recheck_servicenow(config, row, employee, permissions)
        require_write_policy(config, request["group_id"])
        target = preview(db, config, tenant, row.employee_id, request["group_id"], request["add"],
                         request["user_id"] if direct or request.get("remote_subject") else None)
        if not direct and target["employee_id"] == row.reviewer_id:
            raise GraphError("write_conflict")
        if target["user_id"] != request["user_id"]:
            raise GraphError("write_conflict")
        graph = make_client()
        graph.check_group(request["group_id"])
        member = graph.has_member(request["group_id"], request["user_id"])
        if member != request["expected"] and not (row.status == "executing" and member == request["add"]):
            raise GraphError("write_conflict")
        if member != request["add"]:
            db.execute(changes.update().where(changes.c.id == row.id).values(
                status="executing", attempts=attempts, next_attempt=now + timedelta(seconds=30),
            ))
            audit(db, row, "started", attempt=attempts)
            db.commit()
            graph.change_member(request["group_id"], request["user_id"], request["add"])
            if graph.has_member(request["group_id"], request["user_id"]) != request["add"]:
                raise GraphError("graph_unavailable")
        db.execute(changes.update().where(changes.c.id == row.id).values(status="succeeded", attempts=attempts, error_code=None))
        db.execute(state.update().where(state.c.tenant == tenant, state.c.failures == 0,
                                        state.c.next_run > utcnow()).values(next_run=utcnow()))
        audit(db, row, "succeeded", verified_membership=request["add"])
    except GraphError as error:
        retriable = error.code in {"graph_throttled", "graph_unavailable", "graph_unauthorized", "servicenow_unavailable"} and attempts < 5
        status = row.status if retriable else ("conflict" if error.code == "write_conflict" else "failed")
        if retriable:
            # Once a remote mutation started, retain recovery state across retries.
            status = db.scalar(select(changes.c.status).where(changes.c.id == row.id))
        delay = max(error.retry_after or 0, 30 * 2 ** (attempts - 1))
        db.execute(changes.update().where(changes.c.id == row.id).values(
            status=status, error_code=error.code, attempts=attempts, next_attempt=utcnow() + timedelta(seconds=delay),
        ))
        audit(db, row, "retry" if retriable else status, error_code=error.code, attempt=attempts)
    db.commit()
