from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.routes.auth import get_current_employee
from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.core.database import get_db
from backend.app.models.employee import Employee
from backend.app.models.governance import AccessRequest, AccessReview, AuditEvent, RequestableGroup
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.schemas.employee import EmployeeResponse
from backend.app.schemas.governance import (
    AuditResponse, Joiner, Leaver, Mover, Requestability, RequestCreate, RequestDecision,
    RequestResponse, ReviewCreate, ReviewDecision, ReviewResponse,
)
from backend.app.schemas.group import GroupResponse
from backend.app.services import governance_service as service


router = APIRouter(tags=["Governance"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[Employee, Depends(get_current_employee)]
AccessManager = Annotated[Employee, Depends(require_permission("access:manage"))]
Reviewer = Annotated[Employee, Depends(require_permission("reviews:manage"))]
Auditor = Annotated[Employee, Depends(require_permission("audit:read"))]
JoinOperator = Annotated[Employee, Depends(require_permission("employees:create"))]
MoveOperator = Annotated[Employee, Depends(require_permission("employees:update"))]
LeaveOperator = Annotated[Employee, Depends(require_permission("employees:deactivate"))]
Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[int | None, Query(gt=0)]


def page(db: Session, statement, model, before_id: int | None, limit: int):
    if before_id is not None:
        statement = statement.where(model.id < before_id)
    return db.scalars(statement.order_by(model.id.desc()).limit(limit)).all()


@router.get("/auth/me/permissions", response_model=list[str], tags=["Authentication"])
def my_permissions(db: DB, actor: Actor):
    return db.scalars(effective_permissions(actor.id).distinct().order_by(Permission.code)).all()


@router.get("/access-requests/catalog", response_model=list[GroupResponse])
def request_catalog(db: DB, actor: Actor):
    return db.scalars(
        select(Group).join(RequestableGroup, RequestableGroup.group_id == Group.id)
        .where(Group.is_active.is_(True)).order_by(Group.name)
    ).all()


@router.put("/groups/{group_id}/requestability", response_model=GroupResponse)
def requestability(group_id: int, data: Requestability, db: DB, actor: AccessManager):
    return service.set_requestability(db, actor.id, group_id, data.enabled)


@router.post("/access-requests", response_model=RequestResponse, status_code=201)
def submit_request(data: RequestCreate, db: DB, actor: Actor):
    return service.submit_request(db, actor.id, data.group_id, data.reason)


@router.get("/access-requests", response_model=list[RequestResponse])
def own_requests(db: DB, actor: Actor, before_id: Cursor = None, limit: Limit = 50):
    statement = select(AccessRequest).where(AccessRequest.employee_id == actor.id)
    return page(db, statement, AccessRequest, before_id, limit)


@router.get("/access-requests/queue", response_model=list[RequestResponse])
def approval_queue(db: DB, actor: AccessManager, before_id: Cursor = None, limit: Limit = 50):
    statement = select(AccessRequest).where(AccessRequest.status == "pending")
    return page(db, statement, AccessRequest, before_id, limit)


@router.post("/access-requests/{record_id}/decision", response_model=RequestResponse)
def decide_request(record_id: int, data: RequestDecision, db: DB, actor: AccessManager):
    return service.decide(db, AccessRequest, actor.id, record_id, data.decision, data.note)


@router.post("/access-reviews", response_model=ReviewResponse, status_code=201)
def open_review(data: ReviewCreate, db: DB, actor: Reviewer):
    return service.open_review(db, actor.id, data.employee_id, data.group_id)


@router.get("/access-reviews", response_model=list[ReviewResponse])
def list_reviews(
    db: DB, actor: Reviewer, before_id: Cursor = None, limit: Limit = 50,
    status: Literal["pending", "retained", "revoked", "superseded"] | None = None,
):
    statement = select(AccessReview)
    if status is not None:
        statement = statement.where(AccessReview.status == status)
    return page(db, statement, AccessReview, before_id, limit)


@router.post("/access-reviews/{record_id}/decision", response_model=ReviewResponse)
def decide_review(record_id: int, data: ReviewDecision, db: DB, actor: Reviewer):
    return service.decide(db, AccessReview, actor.id, record_id, data.decision, data.note)


@router.get("/audit-events", response_model=list[AuditResponse])
def audit_events(
    db: DB, actor: Auditor, before_id: Cursor = None, limit: Limit = 50,
    action: Annotated[str | None, Query(max_length=80)] = None,
    actor_id: Annotated[int | None, Query(gt=0)] = None,
):
    statement = select(AuditEvent)
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    if actor_id is not None:
        statement = statement.where(AuditEvent.actor_id == actor_id)
    return page(db, statement, AuditEvent, before_id, limit)


@router.post("/lifecycle/joiner", response_model=EmployeeResponse, status_code=201)
def joiner(data: Joiner, db: DB, operator: JoinOperator, actor: AccessManager):
    return service.join_employee(db, actor.id, data.model_dump(exclude={"group_ids"}), data.group_ids)


@router.post("/lifecycle/{employee_id}/mover", response_model=EmployeeResponse)
def mover(employee_id: int, data: Mover, db: DB, operator: MoveOperator, actor: AccessManager):
    return service.move_employee(
        db, actor.id, employee_id, data.model_dump(exclude={"group_ids", "expected_group_ids"}),
        data.group_ids, data.expected_group_ids,
    )


@router.post("/lifecycle/{employee_id}/leaver", response_model=EmployeeResponse)
def leaver(employee_id: int, data: Leaver, db: DB, operator: LeaveOperator, actor: AccessManager):
    return service.leave_employee(db, actor.id, employee_id, data.reason)
