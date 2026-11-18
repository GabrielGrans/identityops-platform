from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.authorization import require_permission
from backend.app.core.database import get_db
from backend.app.schemas.permission import (
    PermissionCreate,
    PermissionUpdate,
    PermissionResponse,
)
from backend.app.services import permission_service


router = APIRouter(
    prefix="/permissions",
    tags=["Permissions"],
)


@router.post(
    "",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_permission(
    data: PermissionCreate,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("permissions:manage")),
):
    try:
        return permission_service.create_permission(
            db,
            data.model_dump(),
            actor_id=actor.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.get(
    "",
    response_model=list[PermissionResponse],
    dependencies=[Depends(require_permission("permissions:read"))],
)
def list_permissions(
    db: Session = Depends(get_db),
):
    return permission_service.list_permissions(db)


@router.get(
    "/{permission_id}",
    response_model=PermissionResponse,
    dependencies=[Depends(require_permission("permissions:read"))],
)
def get_permission(
    permission_id: int,
    db: Session = Depends(get_db),
):
    permission = permission_service.get_permission(
        db,
        permission_id,
    )

    if permission is None:
        raise HTTPException(
            status_code=404,
            detail="Permission not found",
        )

    return permission


@router.put(
    "/{permission_id}",
    response_model=PermissionResponse,
)
def update_permission(
    permission_id: int,
    data: PermissionUpdate,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("permissions:manage")),
):
    permission = permission_service.get_permission(
        db,
        permission_id,
    )

    if permission is None:
        raise HTTPException(
            status_code=404,
            detail="Permission not found",
        )

    try:
        return permission_service.update_permission(
            db,
            permission,
            data.model_dump(),
            actor_id=actor.id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.delete(
    "/{permission_id}",
    response_model=PermissionResponse,
)
def deactivate_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    actor=Depends(require_permission("permissions:manage")),
):
    permission = permission_service.get_permission(
        db,
        permission_id,
    )

    if permission is None:
        raise HTTPException(
            status_code=404,
            detail="Permission not found",
        )

    return permission_service.deactivate_permission(
        db,
        permission,
        actor_id=actor.id,
    )
