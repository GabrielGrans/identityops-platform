from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.routes.governance import Cursor, Limit, page
from backend.app.core.authorization import effective_permissions, require_permission
from backend.app.core.config import Settings, settings
from backend.app.core.database import get_db
from backend.app.models.employee import Employee
from backend.app.models.entra import EntraGroup, EntraMembership, EntraSyncRun, EntraUser
from backend.app.schemas.provisioning import ProvisionRequest, ReconciliationRequest, ReconciliationResult
from backend.app.services import provisioning_service
from backend.app.services.enterprise_governance import access_comparison, latest_snapshot, snapshot_groups
from backend.app.models.permission import Permission
from backend.app.services.audit_service import record_event
from backend.app.schemas.entra import EntraStatus, ExternalGroup, ExternalUser, LinkInput, SyncRunResponse, UserAccessResponse
from backend.app.services import entra_service as service
from backend.app.services.graph_client import DirectorySnapshot, GraphClient, GraphConfig, GraphError, MESSAGES, TokenCache


router = APIRouter(prefix="/entra", tags=["Microsoft Entra ID"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[Employee, Depends(require_permission("entra:read"))]
Operator = Annotated[Employee, Depends(require_permission("entra:sync"))]
LinkManager = Annotated[Employee, Depends(require_permission("entra:manage_links"))]
Provisioner = Annotated[Employee, Depends(require_permission("entra:provision_local"))]
Search = Annotated[str | None, Query(max_length=150)]
SnapshotLoader = Callable[[GraphConfig], DirectorySnapshot]
token_cache = TokenCache()


def integration_settings() -> Settings:
    return settings


def load_graph_snapshot(config: GraphConfig) -> DirectorySnapshot:
    with httpx.Client(trust_env=False, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as http:
        return GraphClient(config, http, token_cache).snapshot()


def snapshot_loader() -> SnapshotLoader:
    return load_graph_snapshot


Config = Annotated[Settings, Depends(integration_settings)]
Loader = Annotated[SnapshotLoader, Depends(snapshot_loader)]


def http_error(error: GraphError) -> HTTPException:
    status = {
        "sync_running": 409,
        "graph_throttled": 429,
        "disabled": 503,
        "invalid_configuration": 503,
        "migration_required": 503,
        "storage_failed": 503,
    }.get(error.code, 502)
    headers = None if error.retry_after is None else {"Retry-After": str(error.retry_after)}
    return HTTPException(status, {"code": error.code, "message": str(error)}, headers=headers)


def migrated(db: Session) -> bool:
    tables = set(inspect(db.connection()).get_table_names())
    if not {"identityops_schema_version", "entra_sync_runs", "entra_users", "entra_groups", "entra_memberships"} <= tables:
        return False
    return "user_type" in {column["name"] for column in inspect(db.connection()).get_columns("entra_users")}


def tenant_scope(config: Settings, db: Session) -> str:
    if not config.ENTRA_ENABLED:
        raise http_error(GraphError("disabled"))
    if config.entra_tenant is None:
        raise http_error(GraphError("invalid_configuration"))
    if not migrated(db):
        raise http_error(GraphError("migration_required"))
    return config.entra_tenant


def tenant_runs(tenant_id: str):
    return select(EntraSyncRun).where(EntraSyncRun.tenant_id == tenant_id)


@router.get("/status", response_model=EntraStatus)
def connection_status(db: DB, actor: Reader, config: Config):
    if not config.ENTRA_ENABLED:
        return EntraStatus(state="disabled", message=MESSAGES["disabled"])
    tenant_id = config.entra_tenant
    if tenant_id is None:
        return EntraStatus(state="invalid_configuration", message=MESSAGES["invalid_configuration"])
    if not migrated(db):
        return EntraStatus(state="migration_required", message=MESSAGES["migration_required"])

    statement = tenant_runs(tenant_id).order_by(EntraSyncRun.id.desc()).limit(1)
    latest = db.scalar(statement)
    success = db.scalar(statement.where(EntraSyncRun.status == "completed"))
    state, message = "ready", "Ready for the first synchronization."
    try:
        GraphConfig.from_settings(config)
    except GraphError as error:
        state, message = error.code, str(error)
    else:
        active = db.scalar(select(EntraSyncRun).where(EntraSyncRun.active_slot == 1))
        if active is not None and not service.expired(active):
            state, message = "sync_running", MESSAGES["sync_running"]
        elif latest is not None and latest.status == "completed":
            state, message = "connected", "Microsoft Graph was verified by the last completed synchronization."
        elif latest is not None:
            code = "sync_expired" if latest.status == "running" else latest.error_code
            state, message = "error", MESSAGES.get(code, MESSAGES["storage_failed"])
    return EntraStatus(
        state=state, message=message,
        imported_users=success.users_count if success else None,
        imported_groups=success.groups_count if success else None,
        last_success_at=success.finished_at if success else None,
        latest_run=SyncRunResponse.model_validate(latest) if latest else None,
    )


@router.post("/sync", response_model=SyncRunResponse, status_code=201)
def sync(db: DB, actor: Operator, config: Config, load: Loader):
    try:
        graph = GraphConfig.from_settings(config)
        tenant_scope(config, db)
        return service.synchronize(db, graph.tenant_id, actor.id, lambda: load(graph))
    except GraphError as error:
        raise http_error(error) from None


@router.get("/sync-runs", response_model=list[SyncRunResponse])
def sync_runs(db: DB, actor: Reader, config: Config, before_id: Cursor = None, limit: Limit = 50):
    return page(db, tenant_runs(tenant_scope(config, db)), EntraSyncRun, before_id, limit)


def directory_page(db, statement, model, before_id, limit, search, fields):
    if search and (term := search.strip()):
        statement = statement.where(or_(*(field.icontains(term, autoescape=True) for field in fields)))
    return page(db, statement, model, before_id, limit)


@router.get("/users", response_model=list[ExternalUser])
def users(
    db: DB, actor: Reader, config: Config, before_id: Cursor = None, limit: Limit = 50, search: Search = None,
):
    statement = select(EntraUser).where(EntraUser.tenant_id == tenant_scope(config, db))
    return directory_page(db, statement, EntraUser, before_id, limit, search,
                          [EntraUser.display_name, EntraUser.principal_name, EntraUser.mail, EntraUser.object_id])


@router.get("/users/{object_id}/access", response_model=UserAccessResponse)
def user_access(object_id: UUID, db: DB, actor: Reader, config: Config):
    tenant = tenant_scope(config, db)
    user = db.scalar(select(EntraUser).where(EntraUser.tenant_id == tenant, EntraUser.object_id == str(object_id)))
    if user is None:
        raise HTTPException(404, "The user is not in this tenant snapshot.")
    snapshot = latest_snapshot(db, tenant)
    current = bool(snapshot and user.present and user.last_seen_run_id == snapshot.id)
    groups = db.scalars(
        snapshot_groups(tenant, snapshot.id).join(EntraMembership)
        .where(EntraMembership.user_id == user.id).order_by(EntraGroup.display_name, EntraGroup.id)
    ).all() if current else []
    own = set(db.scalars(effective_permissions(actor.id).where(Permission.code == "access:manage")))
    comparison = None
    if current and own and provisioning_service.snapshot_is_recent(snapshot):
        comparison = access_comparison(db, tenant, snapshot.id, user, groups)
    return {
        "user": ExternalUser.model_validate(user),
        "groups": [ExternalGroup.model_validate(group) for group in groups],
        "comparison": comparison,
        "snapshot_id": snapshot.id if current else None,
    }


@router.get("/groups", response_model=list[ExternalGroup])
def groups(
    db: DB, actor: Reader, config: Config, before_id: Cursor = None, limit: Limit = 50, search: Search = None,
):
    statement = select(EntraGroup).where(EntraGroup.tenant_id == tenant_scope(config, db))
    return directory_page(db, statement, EntraGroup, before_id, limit, search,
                          [EntraGroup.display_name, EntraGroup.object_id])


@router.get("/groups/{object_id}/members", response_model=list[ExternalUser])
def group_members(
    object_id: UUID, db: DB, actor: Reader, config: Config,
    before_id: Cursor = None, limit: Limit = 50, search: Search = None,
):
    tenant_id = tenant_scope(config, db)
    group = db.scalar(select(EntraGroup).where(EntraGroup.tenant_id == tenant_id, EntraGroup.object_id == str(object_id)))
    if group is None:
        raise HTTPException(404, "The group is not in this tenant snapshot.")
    statement = (
        select(EntraUser).join(EntraMembership, EntraMembership.user_id == EntraUser.id)
        .where(EntraMembership.group_id == group.id, EntraUser.tenant_id == tenant_id)
    )
    return directory_page(db, statement, EntraUser, before_id, limit, search,
                          [EntraUser.display_name, EntraUser.principal_name, EntraUser.object_id])


def link(db, model, config, object_id, actor, data):
    try:
        return service.change_link(db, model, tenant_scope(config, db), str(object_id), actor.id, data.local_id)
    except service.LinkError as error:
        raise HTTPException(error.status, {"code": error.code, "message": str(error)}) from None


@router.put("/users/{object_id}/link", response_model=ExternalUser)
def link_user(object_id: UUID, data: LinkInput, db: DB, actor: LinkManager, config: Config):
    return link(db, EntraUser, config, object_id, actor, data)


@router.put("/groups/{object_id}/link", response_model=ExternalGroup)
def link_group(object_id: UUID, data: LinkInput, db: DB, actor: LinkManager, config: Config):
    return link(db, EntraGroup, config, object_id, actor, data)


def require_provisioning_permissions(db: Session, actor: Employee, data: ReconciliationRequest):
    required = {"entra:read", "entra:manage_links"}
    if any(item.action == "create" for item in data.items):
        required.add("employees:create")
    if not required.issubset(set(db.scalars(effective_permissions(actor.id)))):
        raise HTTPException(403, "Additional local reconciliation permissions are required")


@router.post("/reconciliation/preview", response_model=ReconciliationResult)
def preview_reconciliation(data: ReconciliationRequest, db: DB, actor: Provisioner, config: Config):
    require_provisioning_permissions(db, actor, data)
    tenant = tenant_scope(config, db)
    return provisioning_service.inspect_batch(db, tenant, data)[0]


@router.post("/reconciliation/apply", response_model=ReconciliationResult)
def apply_reconciliation(data: ProvisionRequest, db: DB, actor: Provisioner, config: Config):
    require_provisioning_permissions(db, actor, data)
    tenant = tenant_scope(config, db)
    try:
        return provisioning_service.apply_batch(db, actor.id, tenant, data)
    except SQLAlchemyError:
        db.rollback()
        try:
            record_event(db, actor.id, "entra.provision.failed", "entra_users", None, tenant_id=tenant,
                         object_ids=[str(item.object_id) for item in data.items])
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise HTTPException(503, "The batch could not be saved. Preview again before retrying.") from None
