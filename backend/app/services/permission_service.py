from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.associations import group_permissions
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.services.access_state import reset_group_policy
from backend.app.services.audit_service import commit_change


def list_permissions(db: Session):
    statement = select(Permission).order_by(Permission.name)
    return db.scalars(statement).all()


def get_permission(db: Session, permission_id: int):
    return db.get(Permission, permission_id)


def create_permission(db: Session, data: dict, actor_id: int | None = None):
    duplicate = db.scalar(
        select(Permission).where(
            or_(
                Permission.code == data["code"],
                (
                    (Permission.resource == data["resource"])
                    & (Permission.action == data["action"])
                ),
            )
        )
    )

    if duplicate:
        raise ValueError(
            "Permission code or resource/action already exists"
        )

    permission = Permission(**data)

    db.add(permission)
    commit_change(db, actor_id, "permission.create", permission)

    return permission


def reset_linked_group_policies(db: Session, permission_id: int, actor_id: int | None):
    group_ids = db.scalars(
        select(Group.id)
        .join(group_permissions, group_permissions.c.group_id == Group.id)
        .where(group_permissions.c.permission_id == permission_id)
        .order_by(Group.id)
        .with_for_update(of=Group)
    ).all()
    for group_id in group_ids:
        reset_group_policy(db, group_id, actor_id)


def update_permission(
    db: Session,
    permission: Permission,
    data: dict,
    actor_id: int | None = None,
):
    duplicate = db.scalar(
        select(Permission).where(
            or_(
                Permission.code == data["code"],
                (
                    (Permission.resource == data["resource"])
                    & (Permission.action == data["action"])
                ),
            ),
            Permission.id != permission.id,
        )
    )

    if duplicate:
        raise ValueError(
            "Permission code or resource/action already exists"
        )

    permission = db.get(Permission, permission.id, with_for_update=True, populate_existing=True)
    if any(getattr(permission, field) != data[field] for field in ("code", "is_active") if field in data):
        reset_linked_group_policies(db, permission.id, actor_id)
    for field, value in data.items():
        setattr(permission, field, value)

    commit_change(db, actor_id, "permission.update", permission)

    return permission


def deactivate_permission(db: Session, permission: Permission, actor_id: int | None = None):
    permission = db.get(Permission, permission.id, with_for_update=True, populate_existing=True)
    reset_linked_group_policies(db, permission.id, actor_id)
    permission.is_active = False

    commit_change(db, actor_id, "permission.deactivate", permission)

    return permission
