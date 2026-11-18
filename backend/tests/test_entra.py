from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.routes.entra import integration_settings, snapshot_loader
from backend.app.core.config import Settings
from backend.app.main import app
from backend.app.models.employee import Employee
from backend.app.models.entra import EntraBase, EntraMembership, EntraSyncRun, EntraUser
from backend.app.models.governance import AuditEvent
from backend.app.models.permission import Permission
from backend.app.scripts.migrate import upgrade_database
from backend.app.services import entra_service
from backend.app.services.graph_client import DirectorySnapshot, GraphError

from test_graph_client import APP, GROUP, TENANT, USER


OTHER_USER = str(UUID(int=5))
OTHER_TENANT = str(UUID(int=6))


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def snapshot(*, include_user=True):
    users = {
        key: {"object_id": key, "display_name": label, "principal_name": f"{label}@example.test", "mail": None,
              "account_enabled": True}
        for key, label in ((USER, "alpha"), (OTHER_USER, "beta")) if key != USER or include_user
    }
    groups = {GROUP: {"object_id": GROUP, "display_name": "Security group", "security_enabled": True}}
    return DirectorySnapshot(users, groups, {(GROUP, USER)} if include_user else set(), 0)


@pytest.fixture
def integration(client, db_session, test_data, monkeypatch):
    group = test_data["admin_group"]
    for action in ("read", "sync", "manage_links"):
        group.permissions.append(Permission(
            code=f"entra:{action}", name=f"Entra {action}", resource="entra", action=action, is_active=True,
        ))
    db_session.commit()
    config = Settings(SECRET_KEY="unit-test-only", _env_file=None, ENTRA_ENABLED=True,
                      AZURE_TENANT_ID=TENANT, AZURE_CLIENT_ID=APP, AZURE_CLIENT_SECRET="test-placeholder")
    monkeypatch.setitem(app.dependency_overrides, integration_settings, lambda: config)

    def no_network(*args):
        pytest.fail("Graph connector requires an explicit test double")

    monkeypatch.setitem(app.dependency_overrides, snapshot_loader, lambda: no_network)
    return config


@pytest.fixture
def migrated(integration, db_session):
    bind = db_session.get_bind()
    db_session.commit()
    upgrade_database(bind)
    try:
        yield integration
    finally:
        db_session.rollback()
        EntraBase.metadata.drop_all(bind)
        with bind.begin() as connection:
            connection.execute(text("DROP TABLE identityops_schema_version"))


def use_snapshot(monkeypatch, loader=snapshot):
    monkeypatch.setitem(app.dependency_overrides, snapshot_loader, lambda: lambda config: loader())


def run_sync(client, admin_token):
    return client.post("/entra/sync", headers=headers(admin_token))


def test_migration_is_explicit_additive_and_repeatable(client, db_session, admin_token, test_data, integration):
    auth = headers(admin_token)
    assert client.get("/entra/status", headers=auth).json()["state"] == "migration_required"
    assert run_sync(client, admin_token).status_code == 503
    employee_id = test_data["employee"].id
    bind = db_session.get_bind()
    db_session.commit()
    assert "entra_users" not in inspect(bind).get_table_names()
    upgrade_database(bind)
    try:
        upgrade_database(bind)
        assert client.get("/entra/status", headers=auth).json()["state"] == "ready"
        assert db_session.get(Employee, employee_id).status == "active"
    finally:
        db_session.rollback()
        EntraBase.metadata.drop_all(bind)
        with bind.begin() as connection:
            connection.execute(text("DROP TABLE identityops_schema_version"))


def test_protected_and_disabled(client, admin_token, employee_token, integration):
    assert client.get("/entra/status").status_code == 401
    for path in ("/entra/status", "/entra/users", "/entra/groups", "/entra/sync-runs", f"/entra/groups/{GROUP}/members"):
        assert client.get(path, headers=headers(employee_token)).status_code == 403
    assert run_sync(client, employee_token).status_code == 403
    assert client.put(f"/entra/users/{USER}/link", headers=headers(employee_token), json={"local_id": 1}).status_code == 403
    integration.ENTRA_ENABLED = False
    assert client.get("/entra/status", headers=headers(admin_token)).json()["state"] == "disabled"
    assert run_sync(client, admin_token).json()["detail"]["code"] == "disabled"


def test_missing_credentials(client, admin_token, migrated):
    migrated.AZURE_CLIENT_ID = ""
    response = client.get("/entra/status", headers=headers(admin_token))
    assert response.json()["state"] == "invalid_configuration"
    assert run_sync(client, admin_token).json()["detail"]["code"] == "invalid_configuration"
    assert "test-placeholder" not in response.text


def test_sync_idempotent_membership_pagination_and_audit(client, db_session, admin_token, migrated, monkeypatch):
    use_snapshot(monkeypatch)
    auth = headers(admin_token)
    first = run_sync(client, admin_token)
    assert first.status_code == 201, first.text
    assert first.json()["memberships_count"] == 1
    original = client.get("/entra/users", headers=auth).json()
    assert len(original) == 2
    assert run_sync(client, admin_token).status_code == 201
    assert [row["id"] for row in original] == [row["id"] for row in client.get("/entra/users", headers=auth).json()]
    assert db_session.scalar(select(func.count()).select_from(EntraMembership)) == 1
    filtered = client.get("/entra/users?search=ALPHA", headers=auth).json()
    assert [item["object_id"] for item in filtered] == [USER]
    paginated = client.get("/entra/users?limit=1", headers=auth).json()
    second = client.get(f"/entra/users?limit=1&before_id={paginated[0]['id']}", headers=auth).json()
    assert len(second) == 1 and second[0]["id"] != paginated[0]["id"]
    assert [item["object_id"] for item in client.get(f"/entra/groups/{GROUP}/members", headers=auth).json()] == [USER]
    status = client.get("/entra/status", headers=auth).json()
    assert status["state"] == "connected"
    assert status["last_success_at"]
    assert "tenant_id" not in status["latest_run"]
    actions = db_session.scalars(select(AuditEvent.action).order_by(AuditEvent.id)).all()
    assert actions == ["entra.sync.started", "entra.sync.completed"] * 2


def test_links_conflict_group_links_and_disappearing_user(client, db_session, admin_token, test_data, migrated, monkeypatch):
    use_snapshot(monkeypatch)
    assert run_sync(client, admin_token).status_code == 201
    employee_id = test_data["employee"].id
    auth = headers(admin_token)
    path = f"/entra/users/{USER}/link"
    assert client.put(path, headers=auth, json={"local_id": employee_id}).json()["local_employee_id"] == employee_id
    assert client.put(path, headers=auth, json={"local_id": employee_id}).status_code == 200
    assert client.put(path, headers=auth, json={"local_id": test_data["admin"].id}).status_code == 409
    duplicate = client.put(f"/entra/users/{OTHER_USER}/link", headers=auth, json={"local_id": employee_id})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "link_conflict"
    group = client.put(f"/entra/groups/{GROUP}/link", headers=auth, json={"local_id": test_data["admin_group"].id})
    assert group.status_code == 200
    assert group.json()["local_group_id"] == test_data["admin_group"].id
    use_snapshot(monkeypatch, lambda: snapshot(include_user=False))
    assert run_sync(client, admin_token).status_code == 201
    item = client.get(f"/entra/users?search={USER}", headers=auth).json()[0]
    assert item["present"] is False and item["local_employee_id"] == employee_id
    db_session.expire_all()
    assert db_session.get(Employee, employee_id).status == "active"
    assert client.get(f"/entra/groups/{GROUP}/members", headers=auth).json() == []
    assert client.put(path, headers=auth, json={"local_id": None}).json()["local_employee_id"] is None
    assert client.put(path, headers=auth, json={"local_id": employee_id}).status_code == 409


@pytest.mark.parametrize(("code", "status", "retry_after"), [
    ("token_rejected", 502, None), ("membership_forbidden", 502, None), ("graph_throttled", 429, 30),
])
def test_external_failure_preserves_last_snapshot_and_audits(client, db_session, admin_token, migrated, monkeypatch, code, status, retry_after):
    use_snapshot(monkeypatch)
    first = run_sync(client, admin_token).json()

    def fail():
        raise GraphError(code, retry_after)

    use_snapshot(monkeypatch, fail)
    response = run_sync(client, admin_token)
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert response.headers.get("Retry-After") == (str(retry_after) if retry_after else None)
    auth = headers(admin_token)
    assert len(client.get("/entra/users", headers=auth).json()) == 2
    state = client.get("/entra/status", headers=auth).json()
    assert state["state"] == "error"
    assert state["last_success_at"] == first["finished_at"]
    assert state["latest_run"]["error_code"] == code
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "entra.sync.failed"))
    assert event.details == {"error_code": code}


def test_database_partial_write_rolls_back(client, db_session, admin_token, migrated, monkeypatch):
    use_snapshot(monkeypatch)
    assert run_sync(client, admin_token).status_code == 201
    original = entra_service.upsert_directory

    def failing_upsert(db, model, records, tenant_id, run_id):
        if model is not EntraUser:
            raise SQLAlchemyError("private database failure")
        return original(db, model, records, tenant_id, run_id)

    use_snapshot(monkeypatch, lambda: snapshot(include_user=False))
    monkeypatch.setattr(entra_service, "upsert_directory", failing_upsert)
    assert run_sync(client, admin_token).json()["detail"]["code"] == "storage_failed"
    assert db_session.scalar(select(EntraUser.present).where(EntraUser.object_id == USER)) is True
    assert db_session.scalar(select(func.count()).select_from(EntraMembership)) == 1


def test_tenant_isolation_and_stale_lease_recovery(client, db_session, admin_token, test_data, migrated, monkeypatch):
    use_snapshot(monkeypatch)
    assert run_sync(client, admin_token).status_code == 201
    migrated.AZURE_TENANT_ID = OTHER_TENANT
    auth = headers(admin_token)
    assert client.get("/entra/users", headers=auth).json() == []
    assert client.get(f"/entra/groups/{GROUP}/members", headers=auth).status_code == 404
    stale = EntraSyncRun(tenant_id=TENANT, actor_id=test_data["admin"].id, active_slot=1, status="running",
                         started_at=datetime.now(timezone.utc))
    db_session.add(stale)
    db_session.commit()
    assert run_sync(client, admin_token).status_code == 409
    stale.started_at = datetime.now(timezone.utc) - timedelta(minutes=6)
    db_session.commit()
    assert run_sync(client, admin_token).status_code == 201
    db_session.refresh(stale)
    assert stale.status == "failed" and stale.error_code == "sync_expired"
    assert len(client.get("/entra/users", headers=auth).json()) == 2


def test_running_sync_rejects_second_operator_request(client, admin_token, migrated, monkeypatch, db_session):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("Concurrent requests require independent PostgreSQL connections")

    arrived = Event()
    resume = Event()

    def slow_load():
        arrived.set()
        assert resume.wait(10)
        return snapshot()

    use_snapshot(monkeypatch, slow_load)
    with ThreadPoolExecutor(max_workers=1) as workers:
        first = workers.submit(run_sync, client, admin_token)
        try:
            assert arrived.wait(10)
            response = run_sync(client, admin_token)
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "sync_running"
        finally:
            resume.set()
        assert first.result(timeout=10).status_code == 201
