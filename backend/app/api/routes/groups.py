from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.authorization import require_permission
from backend.app.core.database import get_db
from backend.app.schemas.group import (
    GroupCreate,
    GroupUpdate,
    GroupResponse,
)
from backend.app.schemas.permission import PermissionResponse
from backend.app.services import group_service


router = APIRouter(
    prefix="/groups",
    tags=["Groups"],
)


@router.post(
    "",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_group(
    data: GroupCreate,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("groups:manage")),
):
    try:
        return group_service.create_group(
            db,
            data.model_dump(),
            actor_id=actor.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.get(
    "",
    response_model=list[GroupResponse],
    dependencies=[Depends(require_permission("groups:read"))],
)
def list_groups(
    db: Session = Depends(get_db),
):
    return group_service.list_groups(db)


@router.get(
    "/{group_id}",
    response_model=GroupResponse,
    dependencies=[Depends(require_permission("groups:read"))],
)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
):
    group = group_service.get_group(db, group_id)

    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    return group


@router.put(
    "/{group_id}",
    response_model=GroupResponse,
)
def update_group(
    group_id: int,
    data: GroupUpdate,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("groups:manage")),
):
    group = group_service.get_group(db, group_id)

    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    try:
        return group_service.update_group(
            db,
            group,
            data.model_dump(),
            actor_id=actor.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.delete(
    "/{group_id}",
    response_model=GroupResponse,
)
def deactivate_group(
    group_id: int,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("groups:manage")),
):
    group = group_service.get_group(db, group_id)

    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    return group_service.deactivate_group(db, group, actor_id=actor.id)


@router.post(
    "/{group_id}/permissions/{permission_id}",
    response_model=GroupResponse,
)
def assign_permission(
    group_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("access:manage")),
):
    try:
        return group_service.assign_permission(
            db,
            group_id,
            permission_id,
            actor_id=actor.id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete(
    "/{group_id}/permissions/{permission_id}",
    response_model=GroupResponse,
)
def remove_permission(
    group_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("access:manage")),
):
    try:
        return group_service.remove_permission(
            db,
            group_id,
            permission_id,
            actor_id=actor.id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/{group_id}/permissions", response_model=list[PermissionResponse])
def list_group_permissions(
    group_id: int,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("access:manage")),
):
    group = group_service.get_group(db, group_id)
    if group is None:
        raise HTTPException(404, "Group not found")
    return sorted(group.permissions, key=lambda permission: permission.code)
