from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.app.models.employee import Employee
from backend.app.models.governance import AccessRequest, AccessReview, RequestableGroup
from backend.app.models.group import Group


def lock_employee(db: Session, employee_id: int):
    return db.get(Employee, employee_id, with_for_update={"key_share": True}, populate_existing=True)


def lock_group(db: Session, group_id: int):
    return db.get(Group, group_id, with_for_update={"key_share": True}, populate_existing=True)


def close_pending(
    db: Session,
    model: type[AccessRequest] | type[AccessReview],
    actor_id: int | None,
    note: str,
    *,
    employee_id: int | None = None,
    group_id: int | None = None,
):
    statement = update(model).where(model.status == "pending")
    if employee_id is not None:
        statement = statement.where(model.employee_id == employee_id)
    if group_id is not None:
        statement = statement.where(model.group_id == group_id)
    db.execute(statement.values(
        status="superseded",
        decided_by=actor_id,
        decision_note=note,
        decided_at=datetime.now(timezone.utc),
    ))


def reset_group_policy(db: Session, group_id: int, actor_id: int | None):
    policy = db.get(RequestableGroup, group_id)
    if policy is not None:
        db.delete(policy)
    close_pending(db, AccessRequest, actor_id, "Group access policy changed", group_id=group_id)
    close_pending(db, AccessReview, actor_id, "Group access policy changed", group_id=group_id)
