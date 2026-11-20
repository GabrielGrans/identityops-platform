from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.routes.auth import get_current_employee
from backend.app.core.database import get_db
from backend.app.models.associations import employee_groups, group_permissions
from backend.app.models.employee import Employee
from backend.app.models.group import Group
from backend.app.models.permission import Permission


def effective_permissions(employee_id: int):
    return (
        select(Permission.code)
        .join(group_permissions, group_permissions.c.permission_id == Permission.id)
        .join(Group, Group.id == group_permissions.c.group_id)
        .join(employee_groups, employee_groups.c.group_id == Group.id)
        .where(
            employee_groups.c.employee_id == employee_id,
            Group.is_active.is_(True),
            Permission.is_active.is_(True),
        )
    )


def require_permission(permission_code: str):
    return require_any_permission(permission_code)


def require_any_permission(*permission_codes: str):
    def permission_checker(
        current_employee: Employee = Depends(get_current_employee),
        db: Session = Depends(get_db),
    ):
        statement = effective_permissions(current_employee.id).where(Permission.code.in_(permission_codes))
        if db.scalar(statement) is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {' or '.join(permission_codes)}",
            )
        return current_employee

    return permission_checker


def require_delegation(db: Session, actor_id: int | None, codes, *required: str):
    if actor_id is None:
        return
    actor = db.scalar(select(Employee.status).where(Employee.id == actor_id))
    own = set(db.scalars(effective_permissions(actor_id)))
    if actor != "active" or not set(required) <= own:
        raise HTTPException(403, "Permission denied for this operation")
    if "access:delegate" not in own and not set(codes) <= own:
        raise HTTPException(403, "Cannot delegate permissions outside your scope")


def group_codes(groups):
    return {permission.code for group in groups for permission in group.permissions if permission.is_active}


DIRECT_PROVISION = "entra:direct_provision"


def can_direct_provision(db: Session, employee_id: int) -> bool:
    """Require the active local platform role and its explicit permission together."""
    return db.scalar(effective_permissions(employee_id).where(
        Group.code == "IT_ADMINS", Group.name == "IT Administrators", Permission.code == DIRECT_PROVISION,
    )) is not None
