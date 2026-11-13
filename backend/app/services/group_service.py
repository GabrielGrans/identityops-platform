from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.employee import Employee
from backend.app.models.group import Group
from backend.app.models.permission import Permission


def list_groups(db: Session):
    statement = select(Group).order_by(Group.name)
    return db.scalars(statement).all()


def get_group(db: Session, group_id: int):
    return db.get(Group, group_id)


def create_group(db: Session, data: dict):
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
    db.commit()
    db.refresh(group)

    return group


def update_group(db: Session, group: Group, data: dict):
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

    for field, value in data.items():
        setattr(group, field, value)

    db.commit()
    db.refresh(group)

    return group


def deactivate_group(db: Session, group: Group):
    group.is_active = False

    db.commit()
    db.refresh(group)

    return group


def assign_permission(
    db: Session,
    group_id: int,
    permission_id: int,
):
    group = db.get(Group, group_id)
    permission = db.get(Permission, permission_id)

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
        db.commit()
        db.refresh(group)

    return group


def remove_permission(
    db: Session,
    group_id: int,
    permission_id: int,
):
    group = db.get(Group, group_id)

    if group is None:
        raise LookupError("Group not found")

    permission = db.get(Permission, permission_id)

    if permission is None:
        raise LookupError("Permission not found")

    if permission not in group.permissions:
        raise ValueError("Permission is not assigned to this group")

    group.permissions.remove(permission)

    db.commit()
    db.refresh(group)

    return group


def assign_employee(
    db: Session,
    employee_id: int,
    group_id: int,
):
    employee = db.get(Employee, employee_id)
    group = db.get(Group, group_id)

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
        db.commit()
        db.refresh(employee)

    return employee


def remove_employee(
    db: Session,
    employee_id: int,
    group_id: int,
):
    employee = db.get(Employee, employee_id)
    group = db.get(Group, group_id)

    if employee is None:
        raise LookupError("Employee not found")

    if group is None:
        raise LookupError("Group not found")

    if group not in employee.groups:
        raise ValueError("Employee is not a member of this group")

    employee.groups.remove(group)

    db.commit()
    db.refresh(employee)

    return employee
