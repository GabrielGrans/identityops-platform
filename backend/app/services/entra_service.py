from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from itertools import batched

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.models.employee import Employee
from backend.app.models.entra import EntraGroup, EntraMembership, EntraSyncRun, EntraUser
from backend.app.models.group import Group
from backend.app.services.audit_service import record_event
from backend.app.services.graph_client import DirectorySnapshot, GraphError


LEASE = timedelta(minutes=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def expired(run: EntraSyncRun) -> bool:
    started_at = run.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return started_at + LEASE <= utcnow()


def finish_failed(db: Session, run: EntraSyncRun, code: str):
    run.status = "failed"
    run.active_slot = None
    run.finished_at = utcnow()
    run.error_code = code
    record_event(db, run.actor_id, "entra.sync.failed", "entra_sync_runs", run.id, error_code=code)


def start_sync(db: Session, tenant_id: str, actor_id: int | None) -> int:
    try:
        active = db.scalar(select(EntraSyncRun).where(EntraSyncRun.active_slot == 1).with_for_update())
        if active is not None:
            if not expired(active):
                raise GraphError("sync_running")
            finish_failed(db, active, "sync_expired")
            db.flush()
        run = EntraSyncRun(tenant_id=tenant_id, actor_id=actor_id, status="running", active_slot=1)
        db.add(run)
        db.flush()
        run_id = run.id
        record_event(db, actor_id, "entra.sync.started", "entra_sync_runs", run_id)
        db.commit()
        return run_id
    except IntegrityError:
        db.rollback()
        if db.scalar(select(EntraSyncRun.id).where(EntraSyncRun.active_slot == 1)) is not None:
            raise GraphError("sync_running") from None
        raise GraphError("storage_failed") from None
    except SQLAlchemyError:
        db.rollback()
        raise GraphError("storage_failed") from None


def upsert_directory(db: Session, model, records: Iterable[dict], tenant_id: str, run_id: int) -> dict[str, int]:
    insert_for_db = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    ids = {}
    for batch in batched(records, 500):
        statement = insert_for_db(model).values([
            dict(record, tenant_id=tenant_id, last_seen_run_id=run_id, present=True) for record in batch
        ])
        refreshed_fields = {*batch[0], "present", "last_seen_run_id"} - {"object_id"}
        statement = statement.on_conflict_do_update(
            index_elements=[model.tenant_id, model.object_id],
            set_={field: statement.excluded[field] for field in sorted(refreshed_fields)},
        ).returning(model.object_id, model.id)
        ids.update(db.execute(statement).all())

    db.execute(update(model).where(
        model.tenant_id == tenant_id, model.present.is_(True), model.last_seen_run_id != run_id,
    ).values(present=False))
    return ids


def persist_snapshot(db: Session, run: EntraSyncRun, snapshot: DirectorySnapshot, before_commit=None):
    users = upsert_directory(db, EntraUser, snapshot.users.values(), run.tenant_id, run.id)
    groups = upsert_directory(db, EntraGroup, snapshot.groups.values(), run.tenant_id, run.id)
    db.execute(delete(EntraMembership).where(
        EntraMembership.group_id.in_(select(EntraGroup.id).where(EntraGroup.tenant_id == run.tenant_id))
    ))
    edges = (
        {"group_id": groups[group], "user_id": users[user]} for group, user in snapshot.memberships
    )
    for batch in batched(edges, 500):
        db.execute(insert(EntraMembership), list(batch))

    counts = {
        "users_count": len(users), "groups_count": len(groups),
        "memberships_count": len(snapshot.memberships), "skipped_users_count": snapshot.skipped_users,
    }
    for name, value in counts.items():
        setattr(run, name, value)
    run.status = "completed"
    run.active_slot = None
    run.finished_at = utcnow()
    record_event(db, run.actor_id, "entra.sync.completed", "entra_sync_runs", run.id, **counts)
    if before_commit is not None:
        before_commit()
    db.commit()


def synchronize(
    db: Session, tenant_id: str, actor_id: int | None, fetch_snapshot: Callable[[], DirectorySnapshot], *, before_commit=None,
) -> EntraSyncRun:
    run_id = start_sync(db, tenant_id, actor_id)
    try:
        snapshot = fetch_snapshot()
        run = db.get(EntraSyncRun, run_id, with_for_update=True)
        if run.active_slot != 1 or expired(run):
            raise GraphError("sync_expired")
        if before_commit is None:
            persist_snapshot(db, run, snapshot)
        else:
            persist_snapshot(db, run, snapshot, lambda: before_commit(run))
        return run
    except (GraphError, SQLAlchemyError) as error:
        code = error.code if isinstance(error, GraphError) else "storage_failed"
        db.rollback()
        try:
            run = db.get(EntraSyncRun, run_id, with_for_update=True)
            if run.active_slot == 1:
                finish_failed(db, run, code)
                db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise GraphError("storage_failed") from None
        raise GraphError(code, getattr(error, "retry_after", None)) from None


class LinkError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.status = status


def change_link(db: Session, external_model, tenant_id: str, object_id: str, actor_id: int | None, local_id: int | None):
    if external_model is EntraUser:
        local_model, link_field = Employee, EntraUser.local_employee_id
    else:
        local_model, link_field = Group, EntraGroup.local_group_id
    row = db.scalar(select(external_model).where(
        external_model.tenant_id == tenant_id, external_model.object_id == object_id,
    ).with_for_update())
    if row is None:
        raise LinkError("external_object_missing", "The external object is not in this tenant snapshot.", 404)
    existing = getattr(row, link_field.key)
    if local_id == existing:
        return row
    if local_id is not None:
        if existing is not None or not row.present:
            raise LinkError("link_conflict", "Unlink the existing mapping first. Only present objects can be linked.", 409)
        if db.get(local_model, local_id) is None:
            raise LinkError("local_object_missing", "The local IAM record does not exist.", 404)
    setattr(row, link_field.key, local_id)
    action = "entra.link.removed" if local_id is None else "entra.link.created"
    record_event(db, actor_id, action, external_model.__tablename__, row.id,
                 local_id=existing if local_id is None else local_id, tenant_id=tenant_id, object_id=object_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise LinkError("link_conflict", "This local record is already linked to another object in the tenant.", 409) from None
    return row
