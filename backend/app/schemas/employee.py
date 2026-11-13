from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal


class EmployeeCreate(BaseModel):
    employee_number: str = Field(min_length=2, max_length=30)
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    job_title: str = Field(min_length=2, max_length=120)
    department_id: int | None = None
    manager_id: int | None = None


class EmployeeUpdate(BaseModel):
    employee_number: str = Field(min_length=2, max_length=30)
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    job_title: str = Field(min_length=2, max_length=120)
    department_id: int | None = None
    manager_id: int | None = None
    status: Literal["active", "inactive"] = "active"


class EmployeeResponse(BaseModel):
    id: int
    employee_number: str
    first_name: str
    last_name: str
    email: EmailStr
    job_title: str
    status: str
    department_id: int | None
    manager_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
