from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.authorization import group_codes, require_delegation
from backend.app.models.employee import Employee
from backend.app.models.governance import AccessRequest, AccessReview, RequestableGroup
from backend.app.models.group import Group
from backend.app.services import employee_service
from backend.app.services.access_state import close_pending, lock_employee, lock_group
from backend.app.services.audit_service import commit_change, record_event


def active_employee(db: Session, employee_id: int):
    employee = lock_employee(db, employee_id)
    if employee is None:
        raise HTTPException(404, "Employee not found")
    if employee.status != "active":
        raise HTTPException(409, "Employee is inactive")
    return employee


def active_group(db: Session, group_id: int):
    group = lock_group(db, group_id)
    if group is None:
        raise HTTPException(404, "Group not found")
    if not group.is_active:
        raise HTTPException(409, "Group is inactive")
    return group


def set_requestability(db: Session, actor_id: int, group_id: int, enabled: bool):
    group = active_group(db, group_id)
    policy = db.get(RequestableGroup, group_id)
    if enabled and policy is None:
        require_delegation(db, actor_id, group_codes([group]), "access:manage")
        db.add(RequestableGroup(group_id=group_id))
        record_event(db, actor_id, "group.requestable.enabled", "groups", group_id)
    if not enabled and policy is not None:
        db.delete(policy)
        close_pending(db, AccessRequest, actor_id, "Group closed to requests", group_id=group_id)
        record_event(db, actor_id, "group.requestable.disabled", "groups", group_id)
    db.commit()
    return group


def ensure_pending_unique(db: Session, model, employee_id: int, group_id: int):
    existing = db.scalar(select(model.id).where(
        model.employee_id == employee_id,
        model.group_id == group_id,
        model.status == "pending",
    ))
    if existing is not None:
        raise HTTPException(409, "A pending record already exists")


def submit_request(db: Session, actor_id: int, group_id: int, reason: str):
    employee = active_employee(db, actor_id)
    group = active_group(db, group_id)
    if db.get(RequestableGroup, group_id) is None:
        raise HTTPException(409, "Group does not accept requests")
    if group in employee.groups:
        raise HTTPException(409, "Employee already belongs to this group")
    ensure_pending_unique(db, AccessRequest, actor_id, group_id)

    request = AccessRequest(employee_id=actor_id, group_id=group_id, reason=reason)
    db.add(request)
    commit_change(db, actor_id, "request.submitted", request, employee_id=actor_id, group_id=group_id)
    return request


def open_review(db: Session, actor_id: int, employee_id: int, group_id: int):
    if actor_id == employee_id:
        raise HTTPException(403, "You cannot review your own access")
    employee = active_employee(db, employee_id)
    group = active_group(db, group_id)
    if group not in employee.groups:
        raise HTTPException(409, "Employee does not belong to this group")
    ensure_pending_unique(db, AccessReview, employee_id, group_id)

    review = AccessReview(employee_id=employee_id, group_id=group_id, opened_by=actor_id)
    db.add(review)
    commit_change(db, actor_id, "review.opened", review, employee_id=employee_id, group_id=group_id)
    return review


def decide(db: Session, model, actor_id: int, record_id: int, decision: str, note: str):
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(404, "Workflow record not found")
    if actor_id == record.employee_id:
        raise HTTPException(403, "You cannot decide on your own access")
    if record.status != "pending":
        raise HTTPException(409, "Workflow record has already been closed")

    employee = active_employee(db, record.employee_id)
    group = active_group(db, record.group_id)
    db.refresh(record)
    if record.status != "pending":
        raise HTTPException(409, "Workflow record has already been closed")

    if model is AccessRequest:
        if decision == "approved":
            if db.get(RequestableGroup, group.id) is None or group in employee.groups:
                raise HTTPException(409, "Group access is no longer available for this request")
            require_delegation(db, actor_id, group_codes([group]))
            employee.groups.append(group)
        action = f"request.{decision}"
    else:
        if group not in employee.groups:
            raise HTTPException(409, "Membership has changed")
        if decision == "revoked":
            employee.groups.remove(group)
        action = f"review.{decision}"

    record.status = decision
    record.decided_by = actor_id
    record.decision_note = note
    record.decided_at = datetime.now(timezone.utc)
    commit_change(db, actor_id, action, record, employee_id=employee.id, group_id=group.id)
    return record


def resolve_groups(db: Session, group_ids: list[int]):
    return [active_group(db, group_id) for group_id in sorted(set(group_ids))]


def join_employee(db: Session, actor_id: int, data: dict, group_ids: list[int]):
    employee_service.lock_reporting_hierarchy(db)
    employee = Employee(**data)
    try:
        employee_service.validate_relationships(db, employee.department_id, employee.manager_id)
        employee_service.validate_unique_fields(db, data)
        employee.groups = resolve_groups(db, group_ids)
        require_delegation(db, actor_id, group_codes(employee.groups), "access:manage")
        db.add(employee)
        commit_change(db, actor_id, "lifecycle.joiner", employee, group_ids=sorted(set(group_ids)))
    except (ValueError, IntegrityError) as error:
        db.rollback()
        detail = str(error) if isinstance(error, ValueError) else "Employee could not be created"
        raise HTTPException(409, detail) from error
    return employee


def move_employee(
    db: Session,
    actor_id: int,
    employee_id: int,
    data: dict,
    group_ids: list[int],
    expected_group_ids: list[int] | None,
):
    if actor_id == employee_id:
        raise HTTPException(403, "You cannot change your own access through a mover event")
    employee_service.lock_reporting_hierarchy(db)
    employee = active_employee(db, employee_id)
    previous_groups = {group.id for group in employee.groups}
    if expected_group_ids is not None and previous_groups != set(expected_group_ids):
        raise HTTPException(409, "Memberships changed. Reload the employee before applying the move.")
    groups = resolve_groups(db, group_ids)
    try:
        employee_service.validate_relationships(db, data["department_id"], data["manager_id"], employee_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error

    require_delegation(db, actor_id, group_codes(group for group in groups if group.id not in previous_groups), "access:manage")
    next_groups = {group.id for group in groups}
    previous = {field: getattr(employee, field) for field in data}
    for field, value in data.items():
        setattr(employee, field, value)
    employee.groups = groups
    if previous != data or previous_groups != next_groups:
        for model in (AccessRequest, AccessReview):
            close_pending(db, model, actor_id, "Employee moved", employee_id=employee_id)
        commit_change(
            db, actor_id, "lifecycle.mover", employee,
            before=previous, after=data,
            added_group_ids=sorted(next_groups - previous_groups),
            removed_group_ids=sorted(previous_groups - next_groups),
        )
    return employee


def leave_employee(db: Session, actor_id: int, employee_id: int, reason: str):
    if actor_id == employee_id:
        raise HTTPException(403, "You cannot offboard your own account")
    employee_service.lock_reporting_hierarchy(db)
    employee = lock_employee(db, employee_id)
    if employee is None:
        raise HTTPException(404, "Employee not found")
    reports = db.scalars(select(Employee).where(Employee.manager_id == employee_id)).all()
    if employee.status == "inactive" and not employee.groups and employee.password_hash is None and not reports:
        return employee

    group_ids = sorted(group.id for group in employee.groups)
    employee.groups.clear()
    employee.status = "inactive"
    employee.password_hash = None
    for model in (AccessRequest, AccessReview):
        close_pending(db, model, actor_id, "Employee offboarded", employee_id=employee_id)
    for report in reports:
        report.manager_id = None
    commit_change(
        db, actor_id, "lifecycle.leaver", employee, reason=reason,
        removed_group_ids=group_ids, detached_report_ids=sorted(report.id for report in reports),
    )
    return employee
