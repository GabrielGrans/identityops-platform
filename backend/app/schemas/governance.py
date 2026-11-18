from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.app.schemas.employee import EmployeeCreate


Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
GroupIds = Annotated[list[Annotated[int, Field(gt=0)]], Field(max_length=200)]


class RequestCreate(BaseModel):
    group_id: int = Field(gt=0)
    reason: Reason


class RequestDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Reason


class ReviewCreate(BaseModel):
    employee_id: int = Field(gt=0)
    group_id: int = Field(gt=0)


class ReviewDecision(BaseModel):
    decision: Literal["retained", "revoked"]
    note: Reason


class Requestability(BaseModel):
    enabled: bool


class Joiner(EmployeeCreate):
    group_ids: GroupIds


class Mover(BaseModel):
    department_id: int | None
    manager_id: int | None
    job_title: str = Field(min_length=2, max_length=120)
    group_ids: GroupIds
    expected_group_ids: list[Annotated[int, Field(gt=0)]] | None = None


class Leaver(BaseModel):
    reason: Reason


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    group_id: int
    status: str
    decided_by: int | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class RequestResponse(WorkflowResponse):
    reason: str


class ReviewResponse(WorkflowResponse):
    opened_by: int


class AuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    action: str
    target_type: str
    target_id: int | None
    details: dict
    created_at: datetime
