from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from backend.app.core.authorization import require_permission
from backend.app.core.database import get_db
from backend.app.schemas.group import GroupResponse
from backend.app.services import group_service


router = APIRouter(
    prefix="/employees",
    tags=["Employee Group Memberships"],
)


@router.post(
    "/{employee_id}/groups/{group_id}",
    response_model=GroupResponse,
)
def assign_employee_to_group(
    employee_id: int,
    group_id: int,
    db: Session = Depends(get_db),
    current_employee=Depends(require_permission("access:manage")),
):
    try:
        employee = group_service.assign_employee(
            db,
            employee_id,
            group_id,
        )

        return next(
            group
            for group in employee.groups
            if group.id == group_id
        )

    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete(
    "/{employee_id}/groups/{group_id}",
)
def remove_employee_from_group(
    employee_id: int,
    group_id: int,
    db: Session = Depends(get_db),
    current_employee=Depends(require_permission("access:manage")),
):
    try:
        employee = group_service.remove_employee(
            db,
            employee_id,
            group_id,
        )

        return {
            "message": "Employee removed from group",
            "employee_id": employee.id,
            "group_id": group_id,
        }

    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
