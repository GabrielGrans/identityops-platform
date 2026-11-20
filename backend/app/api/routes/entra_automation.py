from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import inspect, select, text

from backend.app.api.routes.entra import Config, DB, Reader, tenant_scope
from backend.app.core.authorization import effective_permissions, require_any_permission, require_permission
from backend.app.models.employee import Employee
from backend.app.services.audit_service import record_event
from backend.app.services.entra_access_queue import audit, preview
from backend.app.services.entra_automation_tables import alerts, changes, policies, state
from backend.app.services.entra_service import utcnow
from backend.app.services.graph_client import GraphError

router = APIRouter(prefix="/entra/automation", tags=["Entra automation"])
Requester = Annotated[Employee, Depends(require_permission("entra:request_change"))]
Approver = Annotated[Employee, Depends(require_permission("entra:approve_change"))]
Governance = Annotated[Employee, Depends(require_permission("governance:read"))]
Manager = Annotated[Employee, Depends(require_permission("governance:manage"))]


def scope(db, config):
    tenant = tenant_scope(config, db)
    if not inspect(db.connection()).has_table(state.name):
        raise HTTPException(503, "Apply the Entra automation migration.")
    return tenant


def lock_code(db, key):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int | None = Field(default=None, gt=0)
    user_id: UUID | None = None
    group_id: UUID
    add: bool
    justification: str = Field(min_length=8, max_length=1000)


    @model_validator(mode="after")
    def validate_subject(self):
        if (self.employee_id is None) == (self.user_id is None):
            raise ValueError("Select exactly one employee or Entra user")
        return self


class ConfirmedChange(Change):
    expected_snapshot_id: int = Field(gt=0)


class Decision(BaseModel):
    approve: bool
    note: str = Field(min_length=8, max_length=1000)


class ExceptionRule(BaseModel):
    user_id: UUID
    group_id: UUID
    until: date


class Role(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    job_title: str = Field(default="", max_length=120)
    entra_department: str = Field(default="", max_length=256)
    department_id: int | None = Field(default=None, gt=0)
    employment_status: Literal["active", "inactive", ""] = ""
    approved: list[UUID] = Field(default_factory=list, max_length=100)
    required: list[UUID] = Field(default_factory=list, max_length=100)
    privileged: list[UUID] = Field(default_factory=list, max_length=100)
    forbidden: list[tuple[UUID, UUID]] = Field(default_factory=list, max_length=100)
    exceptions: list[ExceptionRule] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_pairs(self):
        if any(left == right for left, right in self.forbidden):
            raise ValueError("Forbidden pairs require distinct groups")
        return self


class RolePolicy(BaseModel):
    review_days: int = Field(default=30, ge=1, le=365)
    roles: list[Role] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_roles(self):
        if len({role.name.casefold() for role in self.roles}) != len(self.roles):
            raise ValueError("Role names must be unique")
        return self


@router.get("/schedule")
def schedule(db: DB, config: Config, actor: Reader):
    tenant = scope(db, config)
    job = db.execute(select(state.c.next_run, state.c.failures).where(state.c.tenant == tenant)).mappings().one_or_none()
    return dict(job) if job else {"next_run": None, "failures": 0}


def check(db, config, tenant, data):
    try:
        return preview(db, config, tenant, data.employee_id, str(data.group_id), data.add, str(data.user_id) if data.user_id else None)
    except GraphError as error:
        raise HTTPException(409, str(error)) from None


@router.post("/preview")
def preview_change(data: Change, db: DB, config: Config, actor: Requester):
    return check(db, config, scope(db, config), data)


@router.post("/requests", status_code=201)
def create_request(data: ConfirmedChange, db: DB, config: Config, actor: Requester):
    tenant = scope(db, config)
    if len(data.justification.strip()) < 8:
        raise HTTPException(422, "Provide a business justification.")
    request = check(db, config, tenant, data)
    if request["snapshot_id"] != data.expected_snapshot_id:
        raise HTTPException(409, "The snapshot changed; preview the request again.")
    lock_code(db, f"entra-request:{tenant}:{request['user_id']}:{request['group_id']}")
    pending = db.execute(select(changes.c.request).where(changes.c.tenant == tenant,
        changes.c.user_object_id == request["user_id"], changes.c.group_object_id == request["group_id"],
        changes.c.status.in_(("pending", "approved", "executing")), changes.c.expires_at > utcnow())).scalars()
    if any(item["group_id"] == request["group_id"] for item in pending):
        raise HTTPException(409, "An open request already exists for this membership.")
    now = utcnow()
    request["justification"] = data.justification.strip()
    row = db.execute(changes.insert().values(tenant=tenant, employee_id=request["employee_id"], requester_id=actor.id,
        user_object_id=request["user_id"], group_object_id=request["group_id"],
        status="pending", request=request, expires_at=now + timedelta(hours=24), next_attempt=now,
        attempts=0).returning(changes)).mappings().one()
    audit(db, row, "requested", actor.id, operation="add" if data.add else "remove",
          expected_membership=request["expected"])
    db.commit()
    return dict(row)


AnyRequestOperator = Annotated[Employee, Depends(
    require_any_permission(
        "entra:request_change", "entra:approve_change"))]


@router.get("/requests")
def list_requests(db: DB, config: Config, actor: AnyRequestOperator, before_id: int | None = Query(None, gt=0)):
    tenant = scope(db, config)
    approver = "entra:approve_change" in set(db.scalars(effective_permissions(actor.id)))
    statement = select(changes).where(changes.c.tenant == tenant)
    if not approver:
        statement = statement.where(changes.c.requester_id == actor.id)
    if before_id is not None:
        statement = statement.where(changes.c.id < before_id)
    return [dict(row) for row in db.execute(statement.order_by(changes.c.id.desc()).limit(50)).mappings()]


@router.post("/requests/{id}/decision")
def decide(id: int, data: Decision, db: DB, config: Config, actor: Approver):
    tenant = scope(db, config)
    row = db.execute(select(changes).where(changes.c.tenant == tenant, changes.c.id == id)
                     .with_for_update()).mappings().one_or_none()
    if not row:
        raise HTTPException(404, "Provisioning request not found.")
    if actor.id == row.requester_id or actor.id == row.employee_id:
        raise HTTPException(403, "A different reviewer must approve this request.")
    if row.status != "pending" or row.expires_at <= utcnow():
        raise HTTPException(409, "This request cannot be decided anymore.")
    if len(data.note.strip()) < 8:
        raise HTTPException(422, "Provide a decision note.")
    if data.approve:
        current = check(db, config, tenant, Change(employee_id=None if row.request.get("remote_subject") else row.employee_id,
                        user_id=row.request["user_id"] if row.request.get("remote_subject") else None, add=row.request["add"],
                        group_id=row.request["group_id"], justification=row.request["justification"]))
        if current["employee_id"] == actor.id:
            raise HTTPException(403, "A different reviewer must approve this request.")
        if any(current[key] != row.request[key] for key in ("user_id", "expected")):
            raise HTTPException(409, "The current membership differs from the approved preview.")
    status = "approved" if data.approve else "rejected"
    updated = db.execute(changes.update().where(changes.c.id == id).values(
        status=status, reviewer_id=actor.id, next_attempt=utcnow()).returning(changes)).mappings().one()
    audit(db, row, status, actor.id, note=data.note.strip())
    db.commit()
    return dict(updated)


@router.get("/role-policy", response_model=RolePolicy, dependencies=[Depends(require_permission("entra:read"))])
def get_policy(db: DB, config: Config, actor: Governance):
    tenant = scope(db, config)
    return db.scalar(select(policies.c.rules).where(policies.c.tenant == tenant)) or {}


@router.put("/role-policy", response_model=RolePolicy, dependencies=[Depends(require_permission("entra:read"))])
def put_policy(data: RolePolicy, db: DB, config: Config, actor: Manager):
    tenant = scope(db, config)
    lock_code(db, f"entra-role-policy:{tenant}")
    before = db.scalar(select(policies.c.rules).where(policies.c.tenant == tenant))
    rules = data.model_dump(mode="json")
    if before != rules:
        if before is None:
            db.execute(policies.insert().values(tenant=tenant, rules=rules))
        else:
            db.execute(policies.update().where(policies.c.tenant == tenant).values(rules=rules))
        record_event(db, actor.id, "entra.role_policy.updated", "entra_role_policy", None, tenant_id=tenant,
                     before=before, after=rules)
        db.commit()
    return data


@router.get("/notifications", dependencies=[Depends(require_permission("entra:read"))])
def list_alerts(db: DB, config: Config, actor: Governance, unread: bool = False,
                offset: int = Query(0, ge=0), key: str | None = Query(None, pattern="^[a-f0-9]{64}$")):
    tenant = scope(db, config)
    statement = select(alerts.c.key, alerts.c.state, alerts.c.payload).where(alerts.c.tenant == tenant)
    if unread:
        statement = statement.where(alerts.c.state == "unread")
    if key:
        statement = statement.where(alerts.c.key == key)
    return [dict(row) for row in db.execute(statement.order_by(alerts.c.key).offset(offset).limit(50)).mappings()]


@router.put("/notifications/{key}", dependencies=[Depends(require_permission("entra:read"))])
def acknowledge(key: str, db: DB, config: Config, actor: Governance):
    tenant = scope(db, config)
    row = db.execute(alerts.update().where(alerts.c.tenant == tenant, alerts.c.key == key,
                                          alerts.c.state == "unread").values(state="acknowledged")
                     .returning(alerts.c.key)).scalar_one_or_none()
    if row:
        record_event(db, actor.id, "entra.notification.acknowledged", "entra_alerts", None, tenant_id=tenant, key=key)
    db.commit()
    return {"acknowledged": bool(row)}
