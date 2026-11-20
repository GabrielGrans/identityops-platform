"""ServiceNow intake and status, gated by an integration-only credential."""
from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from backend.app.api.routes.entra import Config, DB
from backend.app.api.routes.entra_automation import enqueue, lock_code, scope
from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.models.employee import Employee
from backend.app.services.audit_service import record_event
from backend.app.services.entra_access_queue import preview
from backend.app.services.entra_automation_tables import changes
from backend.app.services.entra_service import utcnow
from backend.app.services.graph_client import GraphError
from backend.app.services.servicenow_client import ServiceNowError, SysID, fetch_approval, instance
from backend.app.services.servicenow_tables import requests

router = APIRouter(prefix="/integrations/servicenow/access-requests", tags=["ServiceNow"])
bearer = HTTPBearer(auto_error=False)
Credential = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
Operator = Annotated[Employee, Depends(require_permission("entra:approve_change"))]


class Intake(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sys_id: SysID


def integration_scope(db, config):
    if not config.SERVICENOW_ENABLED:
        raise HTTPException(503, "ServiceNow integration is disabled.")
    try:
        host = instance(config)
    except ServiceNowError as error:
        raise HTTPException(error.status, str(error)) from None
    tenant = scope(db, config)
    if not inspect(db.connection()).has_table(requests.name):
        raise HTTPException(503, "Apply the ServiceNow intake migration.")
    return tenant, host


def integration_auth(config: Config, credentials: Credential):
    expected = config.SERVICENOW_INTAKE_TOKEN.get_secret_value().encode()
    if not config.SERVICENOW_ENABLED:
        raise HTTPException(503, "ServiceNow integration is disabled.")
    if len(expected) < 32:
        raise HTTPException(503, "ServiceNow integration is not configured.")
    if credentials is None or not compare_digest(expected, credentials.credentials.encode()):
        raise HTTPException(401, "Invalid integration credential.", headers={"WWW-Authenticate": "Bearer"})


def scoped_requests(tenant, host):
    return select(requests).where(requests.c.tenant == tenant, requests.c.instance == host)


def result(db, row):
    operation = None
    if row.change_id:
        operation = db.execute(select(changes.c.status, changes.c.error_code).where(
            changes.c.tenant == row.tenant, changes.c.id == row.change_id,
        )).one_or_none()
    return {
        "sys_id": row.sys_id, "ritm": row.ritm, "change_id": row.change_id,
        "status": (operation.status if operation else "failed") if row.change_id else "simulated",
        "error_code": operation.error_code if operation else None,
        "simulated": row.change_id is None, "created_at": row.created_at,
    }


@router.get("/snapshot")
def simulated_requests(db: DB, config: Config, actor: Operator, before: SysID | None = None):
    if not config.SERVICENOW_ENABLED:
        return []
    tenant, host = integration_scope(db, config)
    statement = scoped_requests(tenant, host).where(requests.c.change_id.is_(None))
    if before:
        statement = statement.where(requests.c.sys_id < before)
    rows = db.execute(statement.order_by(requests.c.sys_id.desc()).limit(25)).mappings().all()
    return [result(db, row) | {"evidence": row.evidence} for row in rows]


@router.get("/{sys_id}", dependencies=[Depends(integration_auth)])
def intake_status(sys_id: SysID, db: DB, config: Config):
    tenant, host = integration_scope(db, config)
    row = db.execute(scoped_requests(tenant, host).where(requests.c.sys_id == sys_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "ServiceNow request was not found.")
    return result(db, row)


@router.post("", status_code=201, dependencies=[Depends(integration_auth)])
def submit(data: Intake, response: Response, db: DB, config: Config):
    tenant, host = integration_scope(db, config)
    lookup = scoped_requests(tenant, host).where(requests.c.sys_id == data.sys_id)
    row = db.execute(lookup).mappings().one_or_none()
    if row:
        response.status_code = 200
        return result(db, row)
    try:
        approval = fetch_approval(config, data.sys_id)
    except ServiceNowError as error:
        raise HTTPException(error.status, str(error)) from None

    lock_code(db, f"servicenow:{tenant}:{host}:{data.sys_id}")
    row = db.execute(lookup).mappings().one_or_none()
    if row:
        response.status_code = 200
        return result(db, row)
    actor = db.get(Employee, config.SERVICENOW_REQUESTER_ID) if config.SERVICENOW_REQUESTER_ID else None
    if (not actor or actor.status != "active" or actor.password_hash is not None
            or set(db.scalars(effective_permissions(actor.id))) != {"entra:request_change"}):
        raise HTTPException(503, "Configure a dedicated ServiceNow intake actor.")
    try:
        # Simulation validates the same directory restrictions without enabling any worker operation.
        policy = config.model_copy(update={"ENTRA_WRITE_ENABLED": True}) if config.SERVICENOW_SIMULATION else config
        request = preview(db, policy, tenant, None, str(approval.group_object_id), approval.operation == "grant",
                          str(approval.user_object_id))
    except GraphError as error:
        raise HTTPException(409, str(error)) from None
    if request["employee_id"] == actor.id:
        raise HTTPException(409, "The integration identity cannot be the beneficiary.")
    evidence = approval.model_dump(mode="json")
    change_id = None
    try:
        if not config.SERVICENOW_SIMULATION:
            request["servicenow"] = evidence | {"instance": host}
            change_id = enqueue(db, tenant, actor.id, request, approval.justification).id
        row = db.execute(requests.insert().values(
            tenant=tenant, instance=host, sys_id=approval.sys_id, ritm=approval.ritm, change_id=change_id,
            created_at=utcnow(), evidence=evidence,
        ).returning(requests)).mappings().one()
        record_event(db, actor.id, "servicenow.simulated" if change_id is None else "servicenow.received",
                     requests.name, change_id, tenant_id=tenant, instance=host, sys_id=approval.sys_id,
                     ritm=approval.ritm, requester_id=approval.requester_id, approver_id=approval.approver_id,
                     beneficiary_id=approval.beneficiary_id, approval_id=approval.approval_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.execute(lookup).mappings().one_or_none()
        if row is None:
            raise HTTPException(409, "A different submission already uses this RITM.") from None
        response.status_code = 200
    return result(db, row)
