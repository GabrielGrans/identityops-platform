from uuid import UUID

from sqlalchemy import select

from backend.app.main import app
from backend.app.models.governance import AuditEvent
from backend.app.services.entra_service import synchronize
from backend.app.services.graph_client import DirectorySnapshot

from test_entra import headers, integration, migrated, snapshot
from test_graph_client import GROUP, TENANT, USER


def test_monitoring_api_exposes_no_access_mutations():
    schema = app.openapi()["paths"]
    writes = {
        (path, method)
        for path, operations in schema.items()
        for method in operations
        if method in {"post", "put", "patch", "delete"}
    }
    assert writes == {("/auth/login", "post"), ("/entra/sync", "post")}


def test_monitoring_tracks_completed_snapshots_and_respects_read_permissions(
    monitoring_client, db_session, migrated, test_data, admin_token,
):
    url = "/v1/dashboard/membership-observations?days=7"
    assert monitoring_client.get(url, headers=headers(admin_token)).status_code == 403

    from backend.app.models.permission import Permission

    permission = db_session.scalar(select(Permission).where(Permission.code == "audit:read"))
    if permission is None:
        permission = Permission(code="audit:read", name="Audit read", resource="audit", action="read", is_active=True)
    test_data["admin_group"].permissions.append(permission)
    db_session.commit()

    def empty():
        original = snapshot()
        return DirectorySnapshot(original.users, original.groups, set(), 0)

    first = synchronize(db_session, TENANT, None, snapshot)
    synchronize(db_session, TENANT, None, empty)
    returned = synchronize(db_session, TENANT, None, snapshot)
    synchronize(db_session, TENANT, None, snapshot)

    another_tenant = str(UUID(int=19))
    synchronize(db_session, another_tenant, None, empty)
    synchronize(db_session, another_tenant, None, snapshot)

    payload = monitoring_client.get(url, headers=headers(admin_token)).json()
    assert payload["month"] == {"grants": 1, "revocations": 1}
    assert payload["series"][-1]["grants"] == 1
    assert payload["series"][-1]["revocations"] == 1
    assert [(row["operation"], row["user_name"], row["group_object_id"]) for row in payload["recent"]] == [
        ("added", "alpha", GROUP), ("removed", "alpha", GROUP),
    ]
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.action.like("entra.membership.%"))).all()
    assert all(row.actor_id is None and row.details["user_object_id"] == USER for row in events)
    assert first.id not in {row.target_id for row in events}
    assert returned.id in {row.target_id for row in events}
