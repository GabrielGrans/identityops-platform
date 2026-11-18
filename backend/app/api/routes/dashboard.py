from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes.governance import Actor, Cursor, DB, Limit
from backend.app.core.authorization import effective_permissions
from backend.app.models.permission import Permission
from backend.app.schemas.dashboard import ActivityCategory, ActivityPage, DashboardSummary, RangeDays
from backend.app.services import dashboard_service as service


router = APIRouter(prefix="/v1/dashboard", tags=["Governance Dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: DB, actor: Actor, response: Response, days: RangeDays = "30"):
    response.headers["Cache-Control"] = "no-store"
    try:
        permissions = set(db.scalars(effective_permissions(actor.id).where(
            Permission.code.in_(service.DASHBOARD_PERMISSIONS)
        )))
        if not permissions:
            raise HTTPException(403, "Dashboard permission required")
        return service.summary(db, permissions, int(days))
    except SQLAlchemyError:
        raise HTTPException(503, "Dashboard data is temporarily unavailable") from None


@router.get("/activity", response_model=ActivityPage)
def activity(
    db: DB, actor: Actor, response: Response, days: RangeDays = "30",
    limit: Limit = 20, before_id: Cursor = None, category: ActivityCategory | None = None,
):
    response.headers["Cache-Control"] = "no-store"
    try:
        if db.scalar(effective_permissions(actor.id).where(Permission.code == "audit:read")) is None:
            raise HTTPException(403, "Audit read permission required")
        return service.activity_page(db, int(days), limit, before_id, category)
    except SQLAlchemyError:
        raise HTTPException(503, "Dashboard activity is temporarily unavailable") from None
