import jwt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import (
    create_access_token,
    verify_password,
)
from backend.app.models.employee import Employee
from backend.app.schemas.auth import (
    LoginRequest,
    TokenResponse,
)
from backend.app.schemas.employee import EmployeeResponse


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_employee(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        employee_id = int(payload.get("sub"))

    except (
        jwt.InvalidTokenError,
        TypeError,
        ValueError,
    ):
        raise unauthorized

    employee = db.get(Employee, employee_id)

    if employee is None or employee.status != "active":
        raise unauthorized

    return employee


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    employee = db.scalar(
        select(Employee).where(
            Employee.email == str(data.email)
        )
    )

    if (
        employee is None
        or employee.password_hash is None
        or not verify_password(
            data.password,
            employee.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if employee.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee account is inactive",
        )

    token = create_access_token(employee.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": (
            settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        ),
    }


@router.get(
    "/me",
    response_model=EmployeeResponse,
)
def get_authenticated_employee(
    current_employee: Employee = Depends(
        get_current_employee
    ),
):
    return current_employee
