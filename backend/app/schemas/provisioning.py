from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.app.schemas.employee import EmployeeCreate


LocalId = Annotated[int, Field(gt=0, le=2_147_483_647)]
FieldOverride = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ReconciliationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_id: UUID
    action: Literal["create", "link"] = "create"
    local_employee_id: LocalId | None = None
    department_id: LocalId | None = None
    employee_number: FieldOverride | None = None
    first_name: FieldOverride | None = None
    last_name: FieldOverride | None = None
    job_title: FieldOverride | None = None
    person_verified: bool = False

    @model_validator(mode="after")
    def validate_action(self):
        if self.action == "create" and self.local_employee_id is not None:
            raise ValueError("A local employee ID is only accepted for linking")
        if self.action == "link" and any(value is not None for value in (
            self.department_id, self.employee_number, self.first_name, self.last_name, self.job_title,
        )):
            raise ValueError("Linking does not accept employee field overrides")
        return self


class ReconciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReconciliationItem] = Field(min_length=1, max_length=25)

    @model_validator(mode="after")
    def distinct_objects(self):
        if len({item.object_id for item in self.items}) != len(self.items):
            raise ValueError("Each Entra object may appear only once per batch")
        return self


class ProvisionRequest(ReconciliationRequest):
    confirmed: Literal[True]
    snapshot_run_id: LocalId


class Proposal(BaseModel):
    employee_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    department_id: int | None = None


class Outcome(BaseModel):
    object_id: UUID
    action: Literal["create", "link"]
    status: Literal[
        "already_linked", "eligible_for_creation", "eligible_for_link", "potential_duplicate",
        "missing_required_data", "unsupported_identity_type", "unavailable_snapshot", "validation_conflict",
        "created", "linked",
    ]
    messages: list[str] = Field(default_factory=list)
    matching_employee_ids: list[int] = Field(default_factory=list)
    local_employee_id: int | None = None
    proposal: Proposal | None = None


class ReconciliationResult(BaseModel):
    snapshot_run_id: int | None
    applied: bool = False
    items: list[Outcome]


def valid_employee(proposal: Proposal):
    return EmployeeCreate.model_validate(proposal.model_dump())
