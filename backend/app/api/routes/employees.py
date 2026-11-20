from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.core.database import get_db
from backend.app.schemas.employee import (
    EmployeeAdminCreate,
    EmployeePassword,
    EmployeeUpdate,
    EmployeeResponse,
)
from backend.app.services import employee_service


class EmployeeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def without_sensitive_validation_input(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                detail = [{key: issue[key] for key in ("loc", "msg", "type")} for issue in error.errors()]
                return JSONResponse(status_code=422, content={"detail": detail})

        return without_sensitive_validation_input


router = APIRouter(
    route_class=EmployeeRoute,
    prefix="/employees",
    tags=["Employees"],
)


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    data: EmployeeAdminCreate,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("employees:create")),
):
    try:
        return employee_service.create_employee(
            db,
            data.model_dump(exclude={"password", "group_ids"}),
            actor_id=actor.id,
            password=data.password.get_secret_value() if data.password is not None else None,
            group_ids=data.group_ids,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.get(
    "",
    response_model=list[EmployeeResponse],
    dependencies=[Depends(require_permission("employees:read"))],
)
def list_employees(
    department_id: int | None = None,
    employee_status: Literal["active", "inactive"] | None = Query(
        default=None,
        alias="status",
    ),
    db: Session = Depends(get_db),
):
    return employee_service.list_employees(
        db,
        department_id,
        employee_status,
    )


@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
    dependencies=[Depends(require_permission("employees:read"))],
)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(
        db,
        employee_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return employee


@router.put(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def update_employee(
    employee_id: int,
    data: EmployeeUpdate,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("employees:update")),
):
    employee = employee_service.get_employee(
        db,
        employee_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    try:
        return employee_service.update_employee(
            db,
            employee,
            data.model_dump(),
            actor_id=actor.id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.delete(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("employees:deactivate")),
):
    employee = employee_service.get_employee(
        db,
        employee_id,
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return employee_service.deactivate_employee(
        db,
        employee,
        actor_id=actor.id,
    )


@router.post("/{employee_id}/activate", response_model=EmployeeResponse)
def activate_employee(
    employee_id: int, db: Session = Depends(get_db),
    actor=Depends(require_permission("employees:update")),
):
    try:
        return employee_service.activate_employee(db, employee_id, actor.id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.put("/{employee_id}/password", status_code=204)
def set_employee_password(
    employee_id: int, data: EmployeePassword, db: Session = Depends(get_db),
    actor=Depends(require_permission("employees:reset_password")),
):
    try:
        employee_service.set_employee_password(db, employee_id, actor.id, data.password.get_secret_value())
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.get("/{employee_id}/permissions", response_model=list[str])
def list_effective_permissions(
    employee_id: int, db: Session = Depends(get_db),
    actor=Depends(require_permission("access:manage")),
):
    employee = employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(404, "Employee not found")
    return sorted(set(db.scalars(effective_permissions(employee_id)))) if employee.status == "active" else []
