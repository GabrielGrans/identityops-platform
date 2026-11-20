from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from backend.app.api.routes.entra import Config, DB, Reader
from backend.app.api.routes.entra_automation import scope
from backend.app.core.authorization import effective_permissions
from backend.app.models.entra import EntraGroup, EntraMembership, EntraUser
from backend.app.models.permission import Permission
from backend.app.services.entra_access_queue import eligibility
from backend.app.services.entra_automation_tables import alerts, changes
from backend.app.services.entra_service import utcnow

router = APIRouter(prefix="/entra/directory", tags=["Unified Entra directory"])
Cursor = Annotated[int | None, Query(gt=0)]
Search = Annotated[str | None, Query(max_length=150)]
Limit = Annotated[int, Query(ge=1, le=100)]
OPEN = ("pending", "approved", "executing")


def searched(statement, query, fields):
    term = query.strip() if query else ""
    if term:
        return statement.where(or_(*(field.icontains(term, autoescape=True) for field in fields)))
    return statement


def paged(db, statement, model, after, limit, serialize):
    if after is not None:
        statement = statement.where(model.id > after)
    rows = db.scalars(statement.order_by(model.id).limit(limit + 1)).all()
    return {
        "items": [serialize(row) for row in rows[:limit]],
        "next_after": rows[limit - 1].id if len(rows) > limit else None,
    }


def user_row(user):
    return {
        "source": "entra", "object_id": user.object_id, "display_name": user.display_name,
        "email": user.mail or user.principal_name, "job_title": user.job_title, "department": user.department,
        "account_enabled": user.account_enabled, "synchronized": user.present, "snapshot_id": user.last_seen_run_id,
        "profile_authority": "external" if user.on_premises_sync_enabled is True else
                             "unknown" if user.on_premises_sync_enabled is None else "cloud_candidate",
        "profile_write_supported": False,
    }


def group_row(db, config, tenant, group):
    return {
        "source": "entra", "object_id": group.object_id, "display_name": group.display_name,
        "description": group.description, "synchronized": group.present,
        "eligibility": eligibility(db, config, tenant, group),
        "membership_count": db.scalar(select(func.count()).select_from(EntraMembership)
          .join(EntraUser).where(EntraMembership.group_id == group.id, EntraUser.present.is_(True))),
    }


def pending(db, tenant, column, object_id):
    return db.execute(select(changes.c.id, changes.c.user_object_id, changes.c.group_object_id, changes.c.status)
        .where(changes.c.tenant == tenant, column == object_id, changes.c.status.in_(OPEN),
               changes.c.expires_at > utcnow()).order_by(changes.c.id.desc()).limit(100)).mappings().all()


def one(db, model, tenant, object_id):
    row = db.scalar(select(model).where(model.tenant_id == tenant, model.object_id == str(object_id)))
    if row is None:
        raise HTTPException(404, "The object is not in this tenant snapshot.")
    return row


@router.get("/users")
def users(db: DB, config: Config, actor: Reader, query: Search = None, after: Cursor = None, limit: Limit = 25):
    tenant = scope(db, config)
    statement = searched(select(EntraUser).where(EntraUser.tenant_id == tenant), query,
        (EntraUser.display_name, EntraUser.mail, EntraUser.principal_name, EntraUser.job_title, EntraUser.department))
    return paged(db, statement, EntraUser, after, limit, user_row)


@router.get("/users/{object_id}")
def user_details(object_id: UUID, db: DB, config: Config, actor: Reader):
    tenant = scope(db, config)
    user = one(db, EntraUser, tenant, object_id)
    groups = db.scalars(select(EntraGroup).join(EntraMembership).where(
        EntraMembership.user_id == user.id, EntraGroup.tenant_id == tenant, EntraGroup.present.is_(True),
        EntraGroup.security_enabled.is_(True),
    ).order_by(EntraGroup.display_name, EntraGroup.id).limit(100)).all()
    can_read_findings = db.scalar(effective_permissions(actor.id).where(
        Permission.code == "governance:read"
    )) is not None
    findings = db.execute(select(alerts.c.key, alerts.c.state, alerts.c.payload)
        .where(alerts.c.tenant == tenant, alerts.c.state != "resolved",
               alerts.c.payload["user_object_id"].as_string() == user.object_id)
        .order_by(alerts.c.key).limit(100)).mappings().all() if can_read_findings else []
    return {**user_row(user), "groups": [group_row(db, config, tenant, group) for group in groups],
            "pending": [dict(row) for row in pending(db, tenant, changes.c.user_object_id, user.object_id)],
            "findings": [dict(row) for row in findings]}


@router.get("/users/{object_id}/groups")
def user_groups(object_id: UUID, db: DB, config: Config, actor: Reader, query: Search = None,
                after: Cursor = None, limit: Limit = 25):
    tenant = scope(db, config)
    user = one(db, EntraUser, tenant, object_id)
    statement = searched(select(EntraGroup).join(EntraMembership).where(
        EntraMembership.user_id == user.id, EntraGroup.tenant_id == tenant, EntraGroup.present.is_(True),
        EntraGroup.security_enabled.is_(True),
    ), query, (EntraGroup.display_name, EntraGroup.description))
    return paged(db, statement, EntraGroup, after, limit, lambda row: group_row(db, config, tenant, row))


@router.get("/groups")
def groups(db: DB, config: Config, actor: Reader, query: Search = None, after: Cursor = None, limit: Limit = 25):
    tenant = scope(db, config)
    statement = searched(select(EntraGroup).where(
        EntraGroup.tenant_id == tenant, EntraGroup.security_enabled.is_(True)),
        query, (EntraGroup.display_name, EntraGroup.description))
    return paged(db, statement, EntraGroup, after, limit, lambda row: group_row(db, config, tenant, row))


@router.get("/groups/{object_id}")
def group_details(object_id: UUID, db: DB, config: Config, actor: Reader, query: Search = None,
                  after: Cursor = None, limit: Limit = 25):
    tenant = scope(db, config)
    group = one(db, EntraGroup, tenant, object_id)
    statement = searched(select(EntraUser).join(EntraMembership).where(
        EntraMembership.group_id == group.id, EntraUser.tenant_id == tenant, EntraUser.present.is_(True)),
        query, (EntraUser.display_name, EntraUser.mail, EntraUser.principal_name, EntraUser.department, EntraUser.job_title))
    return {
        **group_row(db, config, tenant, group),
        "members": paged(db, statement, EntraUser, after, limit, user_row),
        "pending": [dict(row) for row in pending(db, tenant, changes.c.group_object_id, group.object_id)],
    }
