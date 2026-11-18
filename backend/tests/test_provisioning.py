from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.models.employee import Employee
from backend.app.models.entra import EntraSyncRun, EntraUser
from backend.app.models.governance import AuditEvent
from backend.app.models.permission import Permission
from backend.app.services import provisioning_service
from test_entra import integration, migrated  # noqa: F401
from test_graph_client import TENANT


URL = "/entra/reconciliation"
ONE, TWO, THREE, FOUR, FIVE, SIX = [str(UUID(int=value)) for value in range(100, 106)]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def data(db_session, migrated, test_data):
    permission = Permission(code="entra:provision_local", name="Provision", resource="entra", action="provision_local")
    test_data["admin_group"].permissions.append(permission)
    run = EntraSyncRun(tenant_id=TENANT, actor_id=test_data["admin"].id, status="completed",
                       finished_at=datetime.now(timezone.utc))
    db_session.add(run)
    db_session.flush()
    for index, object_id in enumerate((ONE, TWO, THREE, FOUR, FIVE, SIX)):
        db_session.add(EntraUser(
            tenant_id=TENANT if object_id != SIX else str(UUID(int=900)),
            object_id=object_id, last_seen_run_id=run.id, present=True,
            user_type="Guest" if object_id == FOUR else "Member", account_enabled=True,
            employee_type="Employee", mail=(test_data["employee"].email.upper() if object_id == THREE else
                                          f"fixture{index}@example.com"),
            employee_number=f"ENTRA{index}", given_name=None if object_id == FIVE else "Imported",
            surname="Person", job_title="Operator",
        ))
    db_session.commit()
    return run.id, permission


def item(object_id, **fields):
    return {"object_id": object_id, "person_verified": True} | fields


def preview(client, token, *items):
    response = client.post(URL + "/preview", headers=auth(token), json={"items": items})
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, token, run_id, *items):
    return client.post(URL + "/apply", headers=auth(token), json={
        "items": items, "snapshot_run_id": run_id, "confirmed": True,
    })


def test_preview_is_read_only_and_classifies_snapshot(client, admin_token, db_session, data):
    result = preview(client, admin_token, *(item(value) for value in (ONE, THREE, FOUR, FIVE, SIX)))
    assert result["snapshot_run_id"] == data[0]
    assert [entry["status"] for entry in result["items"]] == [
        "eligible_for_creation", "potential_duplicate", "unsupported_identity_type",
        "missing_required_data", "unavailable_snapshot",
    ]
    assert result["items"][0]["proposal"]["employee_number"] == "ENTRA0"
    assert db_session.scalar(select(func.count()).select_from(Employee)) == 3
    assert db_session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    invalid = preview(client, admin_token, item(ONE, department_id=9999))
    assert invalid["items"][0]["status"] == "validation_conflict"


def test_apply_creates_inactive_employee_without_access_and_retries(client, admin_token, db_session, data, test_data):
    run_id, _ = data
    record = item(ONE, department_id=test_data["department"].id)
    response = apply(client, admin_token, run_id, record)
    assert response.status_code == 200
    assert response.json()["applied"] is True
    employee_id = response.json()["items"][0]["local_employee_id"]
    employee = db_session.get(Employee, employee_id)
    assert employee.status == "inactive" and employee.password_hash is None and employee.groups == []
    assert employee.email == "fixture0@example.com"
    assert employee.department_id == test_data["department"].id
    assert db_session.scalar(select(EntraUser.local_employee_id).where(EntraUser.object_id == ONE)) == employee_id
    retry = apply(client, admin_token, run_id, record).json()
    assert retry["items"][0]["status"] == "already_linked"
    assert retry["items"][0]["local_employee_id"] == employee_id
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "entra.provision.created"))
    assert event.target_id == employee_id and event.details == {"tenant_id": TENANT, "object_id": ONE}


def test_explicit_link_preserves_fields_and_rejects_mismatches(client, admin_token, db_session, data, test_data):
    run_id, _ = data
    employee = test_data["employee"]
    saved = (employee.email, employee.status, employee.employee_number)
    bad = apply(client, admin_token, run_id, item(THREE, action="link", local_employee_id=test_data["admin"].id))
    assert bad.json()["applied"] is False
    record = item(THREE, action="link", local_employee_id=employee.id)
    assert preview(client, admin_token, record)["items"][0]["status"] == "eligible_for_link"
    linked = apply(client, admin_token, run_id, record)
    assert linked.json()["items"][0]["status"] == "linked"
    db_session.refresh(employee)
    assert (employee.email, employee.status, employee.employee_number) == saved
    assert apply(client, admin_token, run_id, record).json()["items"][0]["status"] == "already_linked"


def test_permissions_and_confirmation(client, admin_token, employee_token, db_session, data, test_data):
    run_id, permission = data
    assert client.post(URL + "/preview", json={"items": [item(ONE)]}).status_code == 401
    test_data["inactive_permission_group"].permissions.append(permission)
    db_session.commit()
    for action in ("preview", "apply"):
        response = client.post(URL + "/" + action, headers=auth(employee_token),
            json={"items": [item(ONE)]} | ({"confirmed": True, "snapshot_run_id":run_id} if action=="apply" else {}))
        assert response.status_code == 403
    unconfirmed = client.post(URL + "/apply", headers=auth(admin_token),
                              json={"items": [item(ONE)], "snapshot_run_id": run_id})
    assert unconfirmed.status_code == 422
    assert apply(client, admin_token, run_id, item(ONE, person_verified=False)).json()["applied"] is False


def test_reject_stale_snapshot_and_rollback_entire_batch(client, admin_token, db_session, data):
    run_id, _ = data
    changed = apply(client, admin_token, run_id + 1, item(ONE)).json()
    assert changed["items"][0]["status"] == "unavailable_snapshot"
    blocked = apply(client, admin_token, run_id, item(ONE), item(FOUR)).json()
    assert blocked["applied"] is False
    assert blocked["items"][0]["status"] == "eligible_for_creation"
    assert db_session.scalar(select(func.count()).select_from(Employee)) == 3
    run = db_session.get(EntraSyncRun, run_id)
    run.finished_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()
    assert preview(client, admin_token, item(ONE))["items"][0]["status"] == "unavailable_snapshot"


def test_transaction_rolls_back_if_audit_fails_mid_batch(client, admin_token, db_session, data, monkeypatch):
    run_id, _ = data
    record = provisioning_service.record_event

    def fail_second(*args, **kwargs):
        if kwargs.get("object_id") == TWO:
            raise SQLAlchemyError("private storage message")
        record(*args, **kwargs)

    monkeypatch.setattr(provisioning_service, "record_event", fail_second)
    response = apply(client, admin_token, run_id, item(ONE), item(TWO))
    assert response.status_code == 503 and "private storage" not in response.text
    assert db_session.scalar(select(func.count()).select_from(Employee)) == 3
    assert db_session.scalar(select(EntraUser.local_employee_id).where(EntraUser.object_id == ONE)) is None


def test_concurrent_imports_with_same_normalized_email(client, admin_token, db_session, data):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("Requires independent PostgreSQL connections")
    run_id, _ = data
    row = db_session.scalar(select(EntraUser).where(EntraUser.object_id == TWO))
    row.mail = "FIXTURE0@example.com"
    db_session.commit()
    barrier = Barrier(2)

    def run(value):
        barrier.wait(timeout=5)
        return apply(client, admin_token, run_id, item(value)).json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(run, ONE), pool.submit(run, TWO)
        assert sorted([first.result(timeout=15)["applied"], second.result(timeout=15)["applied"]]) == [False, True]
    assert db_session.scalar(select(func.count()).select_from(Employee)) == 4


def test_batch_detects_repeated_numbers_and_retries_mixed_success(client, admin_token, db_session, data, test_data):
    run_id, _ = data
    create = item(ONE)
    duplicate = preview(client, admin_token, create, item(TWO, employee_number="ENTRA0"))
    assert [entry["status"] for entry in duplicate["items"]] == ["validation_conflict", "validation_conflict"]
    link = item(THREE, action="link", local_employee_id=test_data["employee"].id)
    result = apply(client, admin_token, run_id, create, link).json()
    assert result["applied"]
    assert [entry["status"] for entry in result["items"]] == ["created", "linked"]
    retry = apply(client, admin_token, run_id, create, link).json()
    assert [entry["local_employee_id"] for entry in retry["items"]] == [
        entry["local_employee_id"] for entry in result["items"]
    ]
    assert all(entry["status"] == "already_linked" for entry in retry["items"])
    assert db_session.scalar(select(func.count()).select_from(Employee)) == 4
