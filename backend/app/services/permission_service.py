from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.permission import Permission


def list_permissions(db: Session):
    statement = select(Permission).order_by(Permission.name)
    return db.scalars(statement).all()


def get_permission(db: Session, permission_id: int):
    return db.get(Permission, permission_id)


def create_permission(db: Session, data: dict):
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
    db.commit()
    db.refresh(permission)

    return permission


def update_permission(
    db: Session,
    permission: Permission,
    data: dict,
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

    for field, value in data.items():
        setattr(permission, field, value)

    db.commit()
    db.refresh(permission)

    return permission


def deactivate_permission(db: Session, permission: Permission):
    permission.is_active = False

    db.commit()
    db.refresh(permission)

    return permission
