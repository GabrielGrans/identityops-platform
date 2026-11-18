from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


EmployeeId = Annotated[int, Field(gt=0, le=2_147_483_647)]
CampaignStatus = Literal["draft", "active", "completed", "cancelled", "expired"]
ItemStatus = Literal["pending", "retained", "revoked", "superseded", "not_reviewed"]


class ReviewersInput(BaseModel):
    reviewer_ids: list[EmployeeId] = Field(min_length=1, max_length=100)


class CampaignCreate(ReviewersInput):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    owner_id: EmployeeId
    starts_on: date
    due_on: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.due_on < self.starts_on:
            raise ValueError("Due date must be on or after the start date")
        return self


class CampaignTransition(BaseModel):
    action: Literal["activate", "complete", "cancel", "expire"]


class CertificationDecision(BaseModel):
    decision: Literal["retained", "revoked"]
    justification: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    owner_id: int
    starts_on: date
    due_on: date
    status: CampaignStatus
    created_at: datetime
    activated_at: datetime | None
    closed_at: datetime | None


class CampaignDetails(CampaignResponse):
    reviewer_ids: list[int]
    counts: dict[ItemStatus, int]
    can_decide: bool
    available_actions: list[str]


class CertificationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    employee_id: int
    group_id: int
    status: ItemStatus
    reviewer_id: int | None
    justification: str | None
    decided_at: datetime | None


class CertificationItemDetails(CertificationItemResponse):
    employee_name: str
    group_name: str
