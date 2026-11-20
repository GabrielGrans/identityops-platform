from sqlalchemy import select

from backend.app.core.security import verify_password
from backend.app.models.employee import Employee
from backend.app.models.governance import AuditEvent
from backend.app.models.group import Group


TEST_PASSWORD = "test-only passphrase 142"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def employee_payload(**changes):
    return {
        "first_name": "Directory", "last_name": "Fixture", "employee_number": "DIR001",
        "email": "directory.fixture@example.com", "job_title": "Test Analyst",
    } | changes


def authorize(db, test_data, *codes):
    group = Group(name="Directory operators", code="DIRECTORY_OPS",
                  permissions=[test_data["permissions"][code] for code in codes])
    test_data["employee"].groups.append(group)
    db.commit()
    return group


def test_employee_creation_commits_credentials_memberships_and_audit(client, db_session, admin_token, test_data):
    headers = auth(admin_token)
    first = test_data["admin_group"]
    second = test_data["inactive_permission_group"]
    response = client.post("/employees", headers=headers, json=employee_payload(
        password=TEST_PASSWORD, group_ids=[first.id, second.id],
    ))
    assert response.status_code == 201, response.text
    assert "password" not in response.text
    record = db_session.get(Employee, response.json()["id"])
    assert record.password_hash.startswith("$argon2id$")
    assert verify_password(TEST_PASSWORD, record.password_hash)
    assert {group.id for group in record.groups} == {first.id, second.id}
    assert client.post("/auth/login", json={"email": record.email, "password": TEST_PASSWORD}).status_code == 200
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.target_id == record.id)).all()
    actions = [event.action for event in events]
    assert actions.count("employee.group.assigned") == 2
    assert {"employee.create", "employee.password.set"} <= set(actions)
    assert all(TEST_PASSWORD not in str(event.details) for event in events)
    assert client.post("/employees", headers=headers, json=employee_payload(email="different@example.com")).status_code == 400
    assert client.post("/employees", headers=headers, json=employee_payload(
        employee_number="DIR999", email=record.email.upper(),
    )).status_code == 400


def test_invalid_password_or_group_leaves_no_employee(client, db_session, admin_token, test_data):
    headers = auth(admin_token)
    for fields, status in (
        ({"password": "short!"}, 400),
        ({"password": ["secret-array-do-not-echo"]}, 422),
        ({"password": TEST_PASSWORD, "group_ids": [test_data["admin_group"].id, 99999]}, 400),
        ({"status": "inactive", "group_ids": [test_data["admin_group"].id]}, 400),
    ):
        response = client.post("/employees", headers=headers, json=employee_payload(**fields))
        assert response.status_code == status, response.text
        assert "secret" not in response.text
        assert db_session.scalar(select(Employee).where(Employee.employee_number == "DIR001")) is None


def test_password_authorization_and_account_status(client, db_session, admin_token, employee_token, test_data):
    person = test_data["inactive_employee"]
    path = f"/employees/{person.id}"
    payload = {"password": TEST_PASSWORD}
    assert client.put(f"{path}/password", headers=auth(employee_token), json=payload).status_code == 403
    assert client.put(f"{path}/password", headers=auth(admin_token), json=payload).status_code == 204
    assert client.post("/auth/login", json={"email": person.email, **payload}).status_code == 403
    assert client.post(f"{path}/activate", headers=auth(admin_token)).json()["status"] == "active"
    assert client.post("/auth/login", json={"email": person.email, **payload}).status_code == 200
    assert client.put(f"{path}/password", headers=auth(admin_token), json={"password": TEST_PASSWORD + "2"}).status_code == 204
    assert client.post("/auth/login", json={"email": person.email, **payload}).status_code == 401
    assert client.delete(path, headers=auth(admin_token)).json()["status"] == "inactive"
    assert client.get(f"{path}/permissions", headers=auth(admin_token)).json() == []
    assert db_session.scalar(select(AuditEvent).where(
        AuditEvent.target_id == person.id, AuditEvent.action == "employee.password.reset",
    )) is not None


def test_group_creation_edits_permissions_and_members(client, admin_token, test_data):
    headers = auth(admin_token)
    permission_id = test_data["permissions"]["employees:read"].id
    created = client.post("/groups", headers=headers, json={
        "name": "Operations", "code": "OPS", "is_active": True, "permission_ids": [permission_id],
    })
    assert created.status_code == 201, created.text
    path = f"/groups/{created.json()['id']}"
    employee_id = test_data["employee"].id
    employee_path = f"/employees/{employee_id}"
    membership = f"{employee_path}{path}"
    assert client.post(membership, headers=headers).status_code == 200
    assert [row["id"] for row in client.get(f"{path}/members", headers=headers).json()] == [employee_id]
    assert client.get(f"{employee_path}/permissions", headers=headers).json() == ["employees:read"]
    assert client.put(path, headers=headers, json={"name": "Operations updated", "code": "OPS"}).status_code == 200
    assert client.delete(path, headers=headers).status_code == 200
    assert client.get(f"{employee_path}/permissions", headers=headers).json() == []
    assert client.put(path, headers=headers, json={"name": "Operations updated", "code": "OPS"}).status_code == 200
    assert client.delete(f"{path}/permissions/{permission_id}", headers=headers).status_code == 200
    assert client.get(f"{path}/permissions", headers=headers).json() == []
    assert client.post(f"{path}/permissions/{permission_id}", headers=headers).status_code == 200
    assert client.delete(membership, headers=headers).status_code == 200
    assert client.get(f"{path}/members", headers=headers).json() == []


def test_scoped_operator_cannot_grant_admin_access_or_reset_admin_password(
    client, db_session, employee_token, test_data,
):
    headers = auth(employee_token)
    authorize(db_session, test_data, "employees:create", "employees:reset_password",
              "access:manage", "groups:manage", "permissions:manage", "employees:update")
    admin = test_data["admin"]
    group = test_data["admin_group"]
    permission_id = test_data["permissions"]["access:delegate"].id
    target = test_data["employee"]
    low_group = test_data["inactive_permission_group"]
    actions = [
        ("POST", "/employees", employee_payload(group_ids=[group.id])),
        ("POST", f"/employees/{target.id}/groups/{group.id}", None),
        ("PUT", f"/employees/{admin.id}/password", {"password": TEST_PASSWORD}),
        ("POST", f"/groups/{low_group.id}/permissions/{permission_id}", None),
        ("POST", "/groups", {"name": "Elevated group", "code": "ELEVATED", "permission_ids": [permission_id]}),
        ("PUT", f"/groups/{group.id}/requestability", {"enabled": True}),
    ]
    for method, path, payload in actions:
        response = client.request(method, path, headers=headers, json=payload)
        assert response.status_code == 403, (method, path, response.text)
    assert db_session.scalar(select(Employee).where(Employee.employee_number == "DIR001")) is None
    assert client.get(f"/groups/{group.id}/members", headers=headers).status_code == 403
    assert client.post("/groups", headers=headers, json={"name": "Empty group", "code": "EMPTY"}).status_code == 201


def test_access_management_does_not_authorize_permission_changes(client, db_session, employee_token, test_data):
    authorize(db_session, test_data, "access:manage")
    headers = auth(employee_token)
    group_id = test_data["inactive_permission_group"].id
    path = f"/groups/{group_id}/permissions"
    assert client.get(path, headers=headers).status_code == 200
    for method in ("POST", "DELETE"):
        response = client.request(method, f"{path}/{test_data['extra_permission'].id}", headers=headers)
        assert response.status_code == 403


def test_personnel_creator_has_no_credential_or_membership_authority(
    client, db_session, employee_token, test_data,
):
    authorize(db_session, test_data, "employees:create")
    headers = auth(employee_token)
    assert client.post("/employees", headers=headers, json=employee_payload(
        password=TEST_PASSWORD,
    )).status_code == 403
    assert client.post("/employees", headers=headers, json=employee_payload(
        group_ids=[test_data["admin_group"].id],
    )).status_code == 403
    response = client.post("/employees", headers=headers, json=employee_payload())
    assert response.status_code == 201
    employee = db_session.get(Employee, response.json()["id"])
    assert employee.password_hash is None and not employee.groups


def test_scope_applies_when_reactivating_existing_entitlements(
    client, db_session, admin_token, employee_token, test_data,
):
    authorize(db_session, test_data, "employees:update", "groups:manage")
    target = test_data["inactive_employee"]
    elevated = test_data["admin_group"]
    target.groups.append(elevated)
    db_session.commit()
    assert client.post(f"/employees/{target.id}/activate", headers=auth(employee_token)).status_code == 403

    created = client.post("/groups", headers=auth(admin_token), json={
        "name": "Inactive elevated", "code": "INACTIVE_ELEVATED", "is_active": False,
        "permission_ids": [test_data["permissions"]["access:delegate"].id],
    })
    assert created.status_code == 201
    path = f"/groups/{created.json()['id']}"
    response = client.put(path, headers=auth(employee_token), json={
        "name": "Inactive elevated", "code": "INACTIVE_ELEVATED", "is_active": True,
    })
    assert response.status_code == 403
    assert not client.get(path, headers=auth(admin_token)).json()["is_active"]
