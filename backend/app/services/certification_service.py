from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, literal, select, text, update
from sqlalchemy.orm import Session

from backend.app.models.associations import employee_groups
from backend.app.models.certification import CertificationCampaign, CertificationItem, CertificationReviewer
from backend.app.models.employee import Employee
from backend.app.models.governance import AccessReview
from backend.app.models.group import Group
from backend.app.schemas.certification import CampaignCreate, CertificationDecision
from backend.app.services.access_state import close_pending, lock_employee, lock_group
from backend.app.services.audit_service import commit_change


def utcnow():
    return datetime.now(timezone.utc)


def get_campaign(db: Session, campaign_id: int, *, lock: bool = False):
    campaign = db.get(CertificationCampaign, campaign_id, with_for_update=lock or None)
    if campaign is None:
        raise HTTPException(404, "Certification campaign not found")
    return campaign


def assigned_campaigns(employee_id: int):
    return select(CertificationReviewer.campaign_id).where(CertificationReviewer.employee_id == employee_id)


def reviewers(db: Session, campaign_id: int) -> list[int]:
    return list(db.scalars(
        select(CertificationReviewer.employee_id)
        .where(CertificationReviewer.campaign_id == campaign_id)
        .order_by(CertificationReviewer.employee_id)
    ))


def validate_reviewer_ids(db: Session, ids: list[int], owner_id: int | None = None):
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Reviewer IDs must be distinct")
    expected = set(ids)
    if owner_id is not None:
        expected.add(owner_id)
    active = set(db.scalars(select(Employee.id).where(Employee.id.in_(expected), Employee.status == "active")))
    if active != expected:
        raise HTTPException(422, "The owner and all selected reviewers must be active employees")


def write_reviewers(db: Session, campaign_id: int, ids: list[int]):
    db.execute(insert(CertificationReviewer), [{"campaign_id": campaign_id, "employee_id": reviewer} for reviewer in ids])


def create_campaign(db: Session, actor_id: int, data: CampaignCreate):
    if data.due_on < utcnow().date():
        raise HTTPException(422, "Due date cannot be in the past")
    validate_reviewer_ids(db, data.reviewer_ids, data.owner_id)
    campaign = CertificationCampaign(**data.model_dump(exclude={"reviewer_ids"}), status="draft")
    db.add(campaign)
    db.flush()
    write_reviewers(db, campaign.id, data.reviewer_ids)
    commit_change(db, actor_id, "certification.created", campaign, owner_id=data.owner_id,
                  reviewer_ids=sorted(data.reviewer_ids))
    return campaign


def replace_reviewers(db: Session, actor_id: int, campaign_id: int, ids: list[int]):
    campaign = get_campaign(db, campaign_id, lock=True)
    if campaign.status not in ("draft", "active"):
        raise HTTPException(409, "Reviewers can only be changed on draft or active campaigns")
    validate_reviewer_ids(db, ids)
    before = reviewers(db, campaign.id)
    if before != sorted(ids):
        db.execute(delete(CertificationReviewer).where(CertificationReviewer.campaign_id == campaign.id))
        write_reviewers(db, campaign.id, ids)
        commit_change(db, actor_id, "certification.reviewers_changed", campaign, before=before, after=sorted(ids))
    return campaign


def item_counts(db: Session, campaign_id: int) -> dict[str, int]:
    return dict(db.execute(
        select(CertificationItem.status, func.count())
        .where(CertificationItem.campaign_id == campaign_id)
        .group_by(CertificationItem.status)
    ).all())


def available_actions(campaign: CertificationCampaign, pending: int, today):
    if campaign.status == "draft":
        return (["activate"] if campaign.starts_on <= today <= campaign.due_on else []) + ["cancel"]
    if campaign.status == "active":
        if pending == 0:
            return ["complete", "cancel"]
        return ["cancel"] + (["expire"] if today > campaign.due_on else [])
    return []


def activate(db: Session, campaign: CertificationCampaign, now: datetime) -> int:
    # Prevent a concurrent DELETE from missing the newly inserted snapshot item.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("LOCK TABLE employee_groups IN SHARE MODE"))
    memberships = (
        select(literal(campaign.id), employee_groups.c.employee_id, employee_groups.c.group_id, literal("pending"))
        .select_from(employee_groups)
        .join(Employee, Employee.id == employee_groups.c.employee_id)
        .join(Group, Group.id == employee_groups.c.group_id)
        .where(Employee.status == "active", Group.is_active.is_(True))
    )
    db.execute(insert(CertificationItem).from_select(["campaign_id", "employee_id", "group_id", "status"], memberships))
    count = item_counts(db, campaign.id).get("pending", 0)
    if count == 0:
        raise HTTPException(409, "No active memberships are available to certify")
    campaign.status = "active"
    campaign.activated_at = now
    return count


def transition(db: Session, actor_id: int, campaign_id: int, action: str):
    campaign = get_campaign(db, campaign_id, lock=True)
    now = utcnow()
    counts = item_counts(db, campaign.id)
    if action not in available_actions(campaign, counts.get("pending", 0), now.date()):
        raise HTTPException(409, "This transition is unavailable for the current campaign, dates or pending items")
    if action == "activate":
        count = activate(db, campaign, now)
        commit_change(db, actor_id, "certification.activated", campaign, item_count=count)
        return campaign

    campaign.status = {"complete": "completed", "cancel": "cancelled", "expire": "expired"}[action]
    campaign.closed_at = now
    if action in ("cancel", "expire"):
        db.execute(update(CertificationItem).where(
            CertificationItem.campaign_id == campaign.id, CertificationItem.status == "pending",
        ).values(status="not_reviewed"))
    commit_change(db, actor_id, f"certification.{campaign.status}", campaign, counts=item_counts(db, campaign.id))
    return campaign


def decide_item(db: Session, actor_id: int, campaign_id: int, item_id: int, data: CertificationDecision):
    campaign = get_campaign(db, campaign_id, lock=True)
    if actor_id not in reviewers(db, campaign.id):
        raise HTTPException(404, "Certification campaign not found")
    item = db.get(CertificationItem, item_id)
    if item is None or item.campaign_id != campaign.id:
        raise HTTPException(404, "Certification item not found")
    if actor_id == item.employee_id:
        raise HTTPException(403, "You cannot certify your own access")
    if item.status != "pending":
        raise HTTPException(409, "This item is already closed")
    if campaign.status != "active" or not campaign.starts_on <= utcnow().date() <= campaign.due_on:
        raise HTTPException(409, "The campaign is outside its review window")

    employee = lock_employee(db, item.employee_id)
    group = lock_group(db, item.group_id)
    db.refresh(item)
    if item.status != "pending":
        raise HTTPException(409, "This item is already closed")
    now = utcnow()
    if not campaign.starts_on <= now.date() <= campaign.due_on:
        raise HTTPException(409, "The campaign is outside its review window")
    details = {"campaign_id": campaign.id, "employee_id": item.employee_id, "group_id": item.group_id}
    if employee is None or group is None or employee.status != "active" or not group.is_active or group not in employee.groups:
        item.status = "superseded"
        commit_change(db, actor_id, "certification.item_superseded", item, **details)
        return item

    item.status = data.decision
    item.reviewer_id = actor_id
    item.justification = data.justification
    item.decided_at = now
    if data.decision == "revoked":
        # Persist this decision before the DELETE trigger closes other pending items.
        db.flush()
        employee.groups.remove(group)
        close_pending(db, AccessReview, actor_id, "Membership revoked by certification",
                      employee_id=employee.id, group_id=group.id)
    commit_change(db, actor_id, f"certification.item_{data.decision}", item, **details)
    return item
