from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.routes.auth import get_current_employee
from backend.app.core.database import get_db
from backend.app.models.associations import (
    employee_groups,
    group_permissions,
)
from backend.app.models.employee import Employee
from backend.app.models.group import Group
from backend.app.models.permission import Permission


def require_permission(permission_code: str):
    def permission_checker(
        current_employee: Employee = Depends(
            get_current_employee
        ),
        db: Session = Depends(get_db),
    ):
        statement = (
            select(Permission.id)
            .join(
                group_permissions,
                group_permissions.c.permission_id == Permission.id,
            )
            .join(
                Group,
                Group.id == group_permissions.c.group_id,
            )
            .join(
                employee_groups,
                employee_groups.c.group_id == Group.id,
            )
            .where(
                employee_groups.c.employee_id == current_employee.id,
                Group.is_active.is_(True),
                Permission.code == permission_code,
                Permission.is_active.is_(True),
            )
        )

        permission = db.scalar(statement)

        if permission is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission_code}",
            )

        return current_employee

    return permission_checker
