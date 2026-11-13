from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.authorization import require_permission
from backend.app.core.database import get_db
from backend.app.schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
)
from backend.app.services import department_service


router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
)


@router.post(
    "",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("departments:manage"))],
)
def create_department(
    data: DepartmentCreate,
    db: Session = Depends(get_db),
):
    try:
        return department_service.create_department(
            db,
            data.model_dump(),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )


@router.get(
    "",
    response_model=list[DepartmentResponse],
    dependencies=[Depends(require_permission("departments:read"))],
)
def list_departments(
    db: Session = Depends(get_db),
):
    return department_service.list_departments(db)


@router.get(
    "/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(require_permission("departments:read"))],
)
def get_department(
    department_id: int,
    db: Session = Depends(get_db),
):
    department = department_service.get_department(
        db,
        department_id,
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    return department


@router.put(
    "/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(require_permission("departments:manage"))],
)
def update_department(
    department_id: int,
    data: DepartmentUpdate,
    db: Session = Depends(get_db),
):
    department = department_service.get_department(
        db,
        department_id,
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    try:
        return department_service.update_department(
            db,
            department,
            data.model_dump(),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )


@router.delete(
    "/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(require_permission("departments:manage"))],
)
def deactivate_department(
    department_id: int,
    db: Session = Depends(get_db),
):
    department = department_service.get_department(
        db,
        department_id,
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    return department_service.deactivate_department(
        db,
        department,
    )
