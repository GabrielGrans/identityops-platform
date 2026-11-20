from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select
from pydantic import SecretStr

from backend.app.api.routes import servicenow
from backend.app.models.employee import Employee
from backend.app.models.governance import AuditEvent
from backend.app.models.group import Group
from backend.app.services import entra_access_queue
from backend.app.services.entra_automation_tables import changes
from backend.app.services.entra_service import utcnow
from backend.app.services.servicenow_client import ApprovalEvidence, ServiceNowError, fetch_approval
from backend.app.services.servicenow_tables import requests
from test_entra_automation import BASE, GROUP, TENANT, USER, headers, integration, migrated  # noqa: F401
from test_unified_entra_directory import prepare

PATH = "/integrations/servicenow/access-requests"
SYS_ID = "1" * 32
KEY = "fixture-only-" * 3


def evidence(**values):
    return ApprovalEvidence.model_validate({
        "sys_id": SYS_ID, "ritm": "RITM0010001", "tenant_id": TENANT, "requester_id": "2" * 32,
        "beneficiary_id": "3" * 32, "approver_id": "4" * 32, "approval_id": "5" * 32,
        "approval_state": "approved", "user_object_id": USER, "group_object_id": GROUP,
        "operation": "grant", "justification": "Required for the fixture role",
    } | values)


@pytest.fixture
def connected(db_session, test_data, migrated):
    graph = prepare(db_session, migrated, test_data)
    group = Group(name="ServiceNow intake", code="FIXTURE_SNOW", is_active=True)
    # Use the same existing permission code, with no other effective access.
    group.permissions = [row for row in test_data["admin_group"].permissions if row.code == "entra:request_change"]
    actor = Employee(employee_number="SNOW1", first_name="Service", last_name="Now", email="snow@example.test",
                     status="active", password_hash=None, job_title="Integration", groups=[group])
    db_session.add(actor)
    db_session.commit()
    migrated.SERVICENOW_ENABLED = True
    migrated.SERVICENOW_INSTANCE = "devfixture.service-now.com"
    migrated.SERVICENOW_REQUESTER_ID = actor.id
    migrated.SERVICENOW_INTAKE_TOKEN = SecretStr(KEY)
    migrated.SERVICENOW_READ_USER = "fixture"
    migrated.SERVICENOW_READ_PASSWORD = SecretStr("fixture-only")
    return graph


def test_simulation_idempotency_audit_and_scope(client, db_session, connected, migrated, monkeypatch,
                                                admin_token, employee_token):
    migrated.ENTRA_WRITE_ENABLED = False
    calls = []

    def approved(config, sys_id):
        calls.append(sys_id)
        return evidence(sys_id=sys_id)

    monkeypatch.setattr(servicenow, "fetch_approval", approved)
    auth = headers(KEY)
    assert client.post(PATH, headers=headers(admin_token), json={"sys_id": SYS_ID}).status_code == 401
    assert client.post(PATH, headers=auth, json={"sys_id": SYS_ID, "approved": True}).status_code == 422
    first = client.post(PATH, headers=auth, json={"sys_id": SYS_ID})
    assert first.status_code == 201, first.text
    duplicate = client.post(PATH, headers=auth, json={"sys_id": SYS_ID})
    assert duplicate.status_code == 200 and duplicate.json() == first.json()
    assert first.json()["status"] == "simulated" and first.json()["change_id"] is None
    assert calls == [SYS_ID]
    assert client.post(PATH, headers=auth, json={"sys_id": "7" * 32}).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(requests)) == 1
    assert db_session.scalar(select(func.count()).select_from(changes)) == 0
    assert db_session.scalar(select(AuditEvent).where(AuditEvent.action == "servicenow.simulated"))
    assert not connected.writes
    assert client.get(f"{PATH}/snapshot", headers=headers(admin_token)).status_code == 403
    assert client.get(f"{PATH}/snapshot", headers=headers(employee_token)).json()[0]["ritm"] == "RITM0010001"
    migrated.SERVICENOW_INSTANCE = "different.service-now.com"
    assert client.get(f"{PATH}/{SYS_ID}", headers=auth).status_code == 404


@pytest.mark.parametrize("approval_withdrawn", [False, True])
def test_live_intake_uses_existing_approvals_and_worker(client, db_session, connected, migrated, monkeypatch,
                                                        employee_token, approval_withdrawn):
    migrated.SERVICENOW_SIMULATION = False
    auth = headers(KEY)
    monkeypatch.setattr(servicenow, "fetch_approval", lambda *_: evidence())
    migrated.ENTRA_WRITE_ENABLED = False
    assert client.post(PATH, headers=auth, json={"sys_id": SYS_ID}).status_code == 409
    migrated.ENTRA_WRITE_ENABLED = True
    migrated.ENTRA_PROTECTED_GROUP_IDS = GROUP
    assert client.post(PATH, headers=auth, json={"sys_id": SYS_ID}).status_code == 409
    migrated.ENTRA_PROTECTED_GROUP_IDS = ""
    created = client.post(PATH, headers=auth, json={"sys_id": SYS_ID})
    assert created.status_code == 201, created.text
    operation = created.json()["change_id"]
    assert created.json()["status"] == "pending"
    assert not connected.writes
    reviewer = headers(employee_token)
    assert client.post(f"{BASE}/requests/{operation}/decision", headers=auth,
                       json={"approve": True, "note": "Cannot decide"}).status_code == 401
    authorized = client.post(f"{BASE}/requests/{operation}/decision", headers=reviewer,
                             json={"approve": True, "note": "Approved for fixture"})
    assert authorized.status_code == 200, authorized.text
    search = client.get(f"{BASE}/requests", headers=reviewer, params={"query": "RITM0010001"})
    assert search.json()[0]["request"]["servicenow"]["ritm"] == "RITM0010001"

    def unavailable(*_):
        raise ServiceNowError(502, "Temporary")

    monkeypatch.setattr(entra_access_queue, "fetch_approval", unavailable)
    entra_access_queue.execute_due(db_session, migrated, TENANT, connected.client)
    assert not connected.writes
    assert client.get(f"{PATH}/{SYS_ID}", headers=auth).json()["error_code"] == "servicenow_unavailable"
    db_session.execute(changes.update().where(changes.c.id == operation).values(next_attempt=utcnow() - timedelta(seconds=1)))
    db_session.commit()
    monkeypatch.setattr(entra_access_queue, "fetch_approval", lambda *_: evidence(
        **({"approver_id": "9" * 32} if approval_withdrawn else {})))
    entra_access_queue.execute_due(db_session, migrated, TENANT, connected.client)
    status = client.get(f"{PATH}/{SYS_ID}", headers=auth).json()
    if approval_withdrawn:
        assert status["status"] == "failed" and status["error_code"] == "servicenow_approval_changed"
        assert not connected.writes
    else:
        assert status["status"] == "succeeded" and len(connected.writes) == 1
        timeline = client.get(f"{BASE}/requests/{operation}/timeline", headers=reviewer).json()
        assert any(event["verified_membership"] is True for event in timeline)


@pytest.mark.parametrize("problem", ["pending", "wrong_tenant", "self_approval", "redirect"])
def test_servicenow_adapter_checks_authoritative_response(connected, migrated, monkeypatch, problem):
    body = evidence().model_dump(mode="json")
    body.update({
        "pending": {"approval_state": "requested"},
        "wrong_tenant": {"tenant_id": "00000000-0000-0000-0000-000000000919"},
        "self_approval": {"approver_id": body["beneficiary_id"]},
    }.get(problem, {}))
    real_client = httpx.Client

    def respond(request):
        assert str(request.url) == f"https://devfixture.service-now.com/api/identityops/approval/v1/ritm/{SYS_ID}"
        assert request.headers["authorization"].startswith("Basic ")
        if problem == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.invalid"})
        return httpx.Response(200, json={"result": body})

    monkeypatch.setattr(httpx, "Client", lambda **options: real_client(transport=httpx.MockTransport(respond), **options))
    with pytest.raises(ServiceNowError) as error:
        fetch_approval(migrated, SYS_ID)
    assert error.value.status == (502 if problem == "redirect" else 409)
