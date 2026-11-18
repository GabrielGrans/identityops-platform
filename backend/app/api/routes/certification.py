from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from backend.app.api.routes.auth import get_current_employee
from backend.app.api.routes.governance import Cursor, Limit, page
from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.core.database import get_db
from backend.app.models.certification import CertificationCampaign, CertificationItem
from backend.app.models.employee import Employee
from backend.app.models.group import Group
from backend.app.schemas.certification import (
    CampaignCreate,
    CampaignDetails,
    CampaignResponse,
    CampaignStatus,
    CampaignTransition,
    CertificationDecision,
    CertificationItemDetails,
    CertificationItemResponse,
    ItemStatus,
    ReviewersInput,
)
from backend.app.services import certification_service as service


def require_migration(db: Annotated[Session, Depends(get_db)]):
    if not inspect(db.connection()).has_table("certification_campaigns"):
        raise HTTPException(503, "Apply the IdentityOps database migration before using certification campaigns")


router = APIRouter(prefix="/certification-campaigns", tags=["Access Certification"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[Employee, Depends(get_current_employee)]
Manager = Annotated[Employee, Depends(require_permission("certifications:manage"))]
Reviewer = Annotated[Employee, Depends(require_permission("certifications:review"))]


def reader_permissions(db: DB, actor: Actor) -> tuple[int, set[str]]:
    permissions = set(db.scalars(effective_permissions(actor.id)))
    if not permissions.intersection({"certifications:manage", "certifications:review"}):
        raise HTTPException(403, "Certification permission required")
    return actor.id, permissions


Reader = Annotated[tuple[int, set[str]], Depends(reader_permissions)]


def visible_campaign(db: Session, campaign_id: int, reader: tuple[int, set[str]]):
    actor_id, permissions = reader
    campaign = service.get_campaign(db, campaign_id)
    assigned = service.reviewers(db, campaign.id)
    manager = "certifications:manage" in permissions
    can_decide = "certifications:review" in permissions and actor_id in assigned
    if not manager and not can_decide:
        raise HTTPException(404, "Certification campaign not found")
    return campaign, assigned, manager, can_decide


@router.post("", response_model=CampaignResponse, status_code=201)
def create(data: CampaignCreate, db: DB, actor: Manager):
    require_migration(db)
    return service.create_campaign(db, actor.id, data)


@router.get("", response_model=list[CampaignResponse])
def list_campaigns(
    db: DB, reader: Reader, before_id: Cursor = None, limit: Limit = 50, status: CampaignStatus | None = None,
):
    require_migration(db)
    actor_id, permissions = reader
    statement = select(CertificationCampaign)
    if "certifications:manage" not in permissions:
        statement = statement.where(CertificationCampaign.id.in_(service.assigned_campaigns(actor_id)))
    if status is not None:
        statement = statement.where(CertificationCampaign.status == status)
    return page(db, statement, CertificationCampaign, before_id, limit)


@router.get("/{campaign_id}", response_model=CampaignDetails)
def details(campaign_id: int, db: DB, reader: Reader):
    require_migration(db)
    campaign, assigned, manager, can_decide = visible_campaign(db, campaign_id, reader)
    counts = service.item_counts(db, campaign.id)
    today = service.utcnow().date()
    return CampaignDetails(
        **CampaignResponse.model_validate(campaign).model_dump(),
        reviewer_ids=assigned,
        counts=counts,
        can_decide=can_decide and campaign.status == "active" and campaign.starts_on <= today <= campaign.due_on,
        available_actions=service.available_actions(campaign, counts.get("pending", 0), today) if manager else [],
    )


@router.put("/{campaign_id}/reviewers", response_model=CampaignResponse)
def replace_reviewers(campaign_id: int, data: ReviewersInput, db: DB, actor: Manager):
    require_migration(db)
    return service.replace_reviewers(db, actor.id, campaign_id, data.reviewer_ids)


@router.post("/{campaign_id}/transition", response_model=CampaignResponse)
def transition(campaign_id: int, data: CampaignTransition, db: DB, actor: Manager):
    require_migration(db)
    return service.transition(db, actor.id, campaign_id, data.action)


@router.get("/{campaign_id}/items", response_model=list[CertificationItemDetails])
def list_items(
    campaign_id: int, db: DB, reader: Reader,
    before_id: Cursor = None, limit: Limit = 50, status: ItemStatus | None = None,
):
    require_migration(db)
    visible_campaign(db, campaign_id, reader)
    statement = (
        select(CertificationItem, Employee.first_name, Employee.last_name, Group.name)
        .join(Employee, Employee.id == CertificationItem.employee_id)
        .join(Group, Group.id == CertificationItem.group_id)
        .where(CertificationItem.campaign_id == campaign_id)
    )
    if before_id is not None:
        statement = statement.where(CertificationItem.id < before_id)
    if status is not None:
        statement = statement.where(CertificationItem.status == status)
    rows = db.execute(statement.order_by(CertificationItem.id.desc()).limit(limit))
    return [
        CertificationItemDetails(
            **CertificationItemResponse.model_validate(item).model_dump(),
            employee_name=f"{first_name} {last_name}", group_name=group_name,
        )
        for item, first_name, last_name, group_name in rows
    ]


@router.post("/{campaign_id}/items/{item_id}/decision", response_model=CertificationItemResponse)
def decide(campaign_id: int, item_id: int, data: CertificationDecision, db: DB, actor: Reviewer):
    require_migration(db)
    return service.decide_item(db, actor.id, campaign_id, item_id, data)
