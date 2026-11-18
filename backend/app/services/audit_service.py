from sqlalchemy.orm import Session

from backend.app.models.governance import AuditEvent


def record_event(
    db: Session,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None,
    **details,
):
    db.add(AuditEvent(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    ))


def commit_change(db: Session, actor_id: int | None, action: str, target, **details):
    if actor_id is not None:
        db.flush()
        record_event(db, actor_id, action, target.__tablename__, target.id, **details)
    db.commit()
    db.refresh(target)
