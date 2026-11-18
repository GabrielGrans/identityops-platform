from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.governance import AccessRequest, AccessReview
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.services.access_state import close_pending, lock_employee, lock_group, reset_group_policy
from backend.app.services.audit_service import commit_change


def list_groups(db: Session):
    statement = select(Group).order_by(Group.name)
    return db.scalars(statement).all()


def get_group(db: Session, group_id: int):
    return db.get(Group, group_id)


def create_group(db: Session, data: dict, actor_id: int | None = None):
    duplicate = db.scalar(
        select(Group).where(
            or_(
                Group.name == data["name"],
                Group.code == data["code"],
            )
        )
    )

    if duplicate:
        raise ValueError("Group name or code already exists")

    group = Group(**data)

    db.add(group)
    commit_change(db, actor_id, "group.create", group)

    return group


def update_group(db: Session, group: Group, data: dict, actor_id: int | None = None):
    group = lock_group(db, group.id)
    duplicate = db.scalar(
        select(Group).where(
            or_(
                Group.name == data["name"],
                Group.code == data["code"],
            ),
            Group.id != group.id,
        )
    )

    if duplicate:
        raise ValueError("Group name or code already exists")

    if group.is_active != data.get("is_active", group.is_active):
        reset_group_policy(db, group.id, actor_id)
    for field, value in data.items():
        setattr(group, field, value)

    commit_change(db, actor_id, "group.update", group)

    return group


def deactivate_group(db: Session, group: Group, actor_id: int | None = None):
    group = lock_group(db, group.id)
    reset_group_policy(db, group.id, actor_id)
    group.is_active = False

    commit_change(db, actor_id, "group.deactivate", group)

    return group


def assign_permission(
    db: Session,
    group_id: int,
    permission_id: int,
    actor_id: int | None = None,
):
    permission = db.get(Permission, permission_id, with_for_update=True, populate_existing=True)
    group = lock_group(db, group_id)

    if group is None:
        raise LookupError("Group not found")

    if permission is None:
        raise LookupError("Permission not found")

    if not group.is_active:
        raise ValueError("Cannot assign permission to inactive group")

    if not permission.is_active:
        raise ValueError("Cannot assign inactive permission")

    if permission not in group.permissions:
        group.permissions.append(permission)
        reset_group_policy(db, group_id, actor_id)
        commit_change(db, actor_id, "group.permission.assigned", group, permission_id=permission_id)

    return group


def remove_permission(
    db: Session,
    group_id: int,
    permission_id: int,
    actor_id: int | None = None,
):
    permission = db.get(Permission, permission_id, with_for_update=True, populate_existing=True)
    group = lock_group(db, group_id)

    if group is None:
        raise LookupError("Group not found")

    if permission is None:
        raise LookupError("Permission not found")

    if permission not in group.permissions:
        raise ValueError("Permission is not assigned to this group")

    group.permissions.remove(permission)

    reset_group_policy(db, group_id, actor_id)
    commit_change(db, actor_id, "group.permission.removed", group, permission_id=permission_id)

    return group


def assign_employee(
    db: Session,
    employee_id: int,
    group_id: int,
    actor_id: int | None = None,
):
    employee = lock_employee(db, employee_id)
    group = lock_group(db, group_id)

    if employee is None:
        raise LookupError("Employee not found")

    if group is None:
        raise LookupError("Group not found")

    if employee.status != "active":
        raise ValueError("Cannot assign inactive employee")

    if not group.is_active:
        raise ValueError("Cannot assign inactive group")

    if group not in employee.groups:
        employee.groups.append(group)
        close_pending(db, AccessRequest, actor_id, "Access assigned directly", employee_id=employee_id, group_id=group_id)
        commit_change(db, actor_id, "employee.group.assigned", employee, group_id=group_id)

    return employee


def remove_employee(
    db: Session,
    employee_id: int,
    group_id: int,
    actor_id: int | None = None,
):
    employee = lock_employee(db, employee_id)
    group = lock_group(db, group_id)

    if employee is None:
        raise LookupError("Employee not found")

    if group is None:
        raise LookupError("Group not found")

    if group not in employee.groups:
        raise ValueError("Employee is not a member of this group")

    employee.groups.remove(group)

    close_pending(db, AccessReview, actor_id, "Membership removed", employee_id=employee_id, group_id=group_id)
    commit_change(db, actor_id, "employee.group.removed", employee, group_id=group_id)

    return employee
