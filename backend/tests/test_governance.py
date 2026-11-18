from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select

from backend.app.models import Employee, Group, Permission
from backend.app.models.governance import AuditEvent
from backend.app.services import audit_service
from backend.tests.conftest import test_engine


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def governance(db_session, test_data):
    admin_group = test_data["admin_group"]
    admin_group.permissions.extend([
        Permission(name="Read Audit", code="audit:read", resource="audit", action="read"),
        Permission(name="Manage Reviews", code="reviews:manage", resource="reviews", action="manage"),
    ])
    group = Group(name="Application Users", code="APP_USERS", is_active=True)
    db_session.add(group)
    db_session.commit()
    return group.id


def open_for_requests(client, admin_token, group_id):
    response = client.put(f"/groups/{group_id}/requestability", headers=auth(admin_token), json={"enabled": True})
    assert response.status_code == 200, response.text


def submit(client, token, group_id):
    return client.post("/access-requests", headers=auth(token), json={"group_id": group_id, "reason": "Project work"})


def test_approval_grants_once_and_audits(client, admin_token, employee_token, test_data, governance):
    group_id = governance
    employee_id = test_data["employee"].id
    admin_id = test_data["admin"].id
    assert submit(client, employee_token, group_id).status_code == 409
    assert client.get("/access-requests/queue", headers=auth(employee_token)).status_code == 403
    open_for_requests(client, admin_token, group_id)
    assert [group["id"] for group in client.get("/access-requests/catalog", headers=auth(employee_token)).json()] == [group_id]

    response = submit(client, employee_token, group_id)
    assert response.status_code == 201, response.text
    record = response.json()
    assert submit(client, employee_token, group_id).status_code == 409
    assert client.get("/access-requests", headers=auth(admin_token)).json() == []
    assert client.get("/access-requests/queue", headers=auth(admin_token)).json()[0]["id"] == record["id"]

    path = f"/access-requests/{record['id']}/decision"
    decision = {"decision": "approved", "note": "Verified"}
    assert client.post(path, headers=auth(employee_token), json=decision).status_code == 403
    approved = client.post(path, headers=auth(admin_token), json=decision)
    assert approved.status_code == 200
    assert approved.json()["decided_by"] == admin_id
    assert client.post(path, headers=auth(admin_token), json=decision).status_code == 409
    groups = client.get(f"/employees/{employee_id}/groups", headers=auth(admin_token)).json()
    assert group_id in {group["id"] for group in groups}
    assert client.get("/audit-events", headers=auth(employee_token)).status_code == 403
    audit = client.get("/audit-events", params={"action": "request.approved", "actor_id": admin_id}, headers=auth(admin_token))
    assert audit.status_code == 200
    assert len(audit.json()) == 1
    assert audit.json()[0]["details"] == {"employee_id": employee_id, "group_id": group_id}


def test_self_approval_rejected_and_policy_change_supersedes_requests(client, admin_token, employee_token, test_data, governance):
    open_for_requests(client, admin_token, governance)
    own = submit(client, admin_token, governance).json()
    decision = {"decision": "approved", "note": "Valid justification"}
    assert client.post(f"/access-requests/{own['id']}/decision", headers=auth(admin_token), json=decision).status_code == 403
    other = submit(client, employee_token, governance).json()
    permission_id = test_data["extra_permission"].id
    response = client.post(f"/groups/{governance}/permissions/{permission_id}", headers=auth(admin_token))
    assert response.status_code == 200
    assert client.get("/access-requests/catalog", headers=auth(employee_token)).json() == []
    history = client.get("/access-requests", headers=auth(employee_token)).json()
    assert history[0]["status"] == "superseded"
    assert client.post(f"/access-requests/{other['id']}/decision", headers=auth(admin_token), json=decision).status_code == 409


def test_review_retain_revoke_and_stale_review(client, admin_token, employee_token, test_data, governance):
    employee_id = test_data["employee"].id
    headers = auth(admin_token)
    membership = f"/employees/{employee_id}/groups/{governance}"
    assert client.post(membership, headers=headers).status_code == 200
    payload = {"employee_id": employee_id, "group_id": governance}
    assert client.post("/access-reviews", headers=auth(employee_token), json=payload).status_code == 403
    first = client.post("/access-reviews", headers=headers, json=payload)
    assert first.status_code == 201
    assert client.post("/access-reviews", headers=headers, json=payload).status_code == 409
    path = f"/access-reviews/{first.json()['id']}/decision"
    assert client.post(path, headers=headers, json={"decision": "retained", "note": "Still needed"}).json()["status"] == "retained"

    stale = client.post("/access-reviews", headers=headers, json=payload).json()
    assert client.delete(membership, headers=headers).status_code == 200
    assert client.post(membership, headers=headers).status_code == 200
    assert client.post(f"/access-reviews/{stale['id']}/decision", headers=headers, json={
        "decision": "revoked", "note": "Stale snapshot",
    }).status_code == 409

    final = client.post("/access-reviews", headers=headers, json=payload).json()
    response = client.post(f"/access-reviews/{final['id']}/decision", headers=headers, json={
        "decision": "revoked", "note": "Project ended",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert governance not in {group["id"] for group in client.get(f"/employees/{employee_id}/groups", headers=headers).json()}


def test_lifecycle_reconciles_access_and_disables_existing_token(client, admin_token, employee_token, db_session, test_data, governance):
    headers = auth(admin_token)
    employee_id = test_data["employee"].id
    group_id = governance
    open_for_requests(client, admin_token, group_id)
    assert submit(client, employee_token, group_id).status_code == 201
    join_data = {
        "employee_number": "NEW001", "first_name": "New", "last_name": "Employee",
        "email": "new@example.com", "job_title": "Analyst", "group_ids": [group_id, group_id],
        "manager_id": employee_id,
    }
    assert client.post("/lifecycle/joiner", headers=headers, json={**join_data, "group_ids": [999]}).status_code == 404
    joined = client.post("/lifecycle/joiner", headers=headers, json=join_data)
    assert joined.status_code == 201, joined.text
    new_id = joined.json()["id"]
    assert [group["id"] for group in client.get(f"/employees/{new_id}/groups", headers=headers).json()] == [group_id]

    moved = client.post(f"/lifecycle/{employee_id}/mover", headers=headers, json={
        "department_id": test_data["department"].id, "manager_id": test_data["admin"].id,
        "job_title": "Senior Analyst", "group_ids": [group_id],
    })
    assert moved.status_code == 200, moved.text
    assert moved.json()["job_title"] == "Senior Analyst"
    assert client.get("/access-requests", headers=auth(employee_token)).json()[0]["status"] == "superseded"
    employee_groups = f"/employees/{employee_id}/groups"
    assert [group["id"] for group in client.get(employee_groups, headers=headers).json()] == [group_id]

    leave_url = f"/lifecycle/{employee_id}/leaver"
    assert client.post(leave_url, headers=headers, json={"reason": "Contract ended"}).json()["status"] == "inactive"
    assert client.post(leave_url, headers=headers, json={"reason": "Retried"}).status_code == 200
    assert client.get(employee_groups, headers=headers).json() == []
    assert client.get("/auth/me", headers=auth(employee_token)).status_code == 401
    assert client.get(f"/employees/{new_id}", headers=headers).json()["manager_id"] is None
    db_session.expire_all()
    assert db_session.get(Employee, employee_id).password_hash is None
    assert len(db_session.scalars(select(AuditEvent).where(AuditEvent.action == "lifecycle.leaver")).all()) == 1


def test_audit_failure_rolls_back_joiner(client, admin_token, db_session, governance, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Audit persistence failed")

    monkeypatch.setattr(audit_service, "record_event", fail)
    with pytest.raises(RuntimeError, match="Audit persistence"):
        client.post("/lifecycle/joiner", headers=auth(admin_token), json={
            "employee_number": "ROLLBACK", "first_name": "New", "last_name": "Employee",
            "email": "rollback@example.com", "job_title": "Analyst", "group_ids": [governance],
        })
    assert db_session.scalar(select(Employee).where(Employee.employee_number == "ROLLBACK")) is None


@pytest.mark.skipif(test_engine.dialect.name != "postgresql", reason="PostgreSQL row locks required")
def test_concurrent_approvals_commit_one_decision(client, admin_token, employee_token, governance):
    open_for_requests(client, admin_token, governance)
    record_id = submit(client, employee_token, governance).json()["id"]
    barrier = Barrier(2, timeout=5)

    def decide():
        barrier.wait()
        return client.post(f"/access-requests/{record_id}/decision", headers=auth(admin_token), json={
            "decision": "approved", "note": "Approved concurrently",
        }).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [pool.submit(decide) for _ in range(2)]
        assert sorted(future.result(timeout=10) for future in attempts) == [200, 409]


def test_effective_permission_list_is_sorted_and_excludes_inactive_grants(client, admin_token, employee_token, governance):
    result = client.get("/auth/me/permissions", headers=auth(admin_token))
    assert result.status_code == 200
    assert result.json() == sorted(set(result.json()))
    assert {"audit:read", "reviews:manage", "access:manage"} <= set(result.json())
    assert client.get("/auth/me/permissions", headers=auth(employee_token)).json() == []


def test_rejected_request_does_not_create_membership(client, admin_token, employee_token, test_data, governance):
    open_for_requests(client, admin_token, governance)
    record_id = submit(client, employee_token, governance).json()["id"]
    response = client.post(f"/access-requests/{record_id}/decision", headers=auth(admin_token), json={
        "decision": "rejected", "note": "Access is out of scope",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    employee_id = test_data["employee"].id
    groups = client.get(f"/employees/{employee_id}/groups", headers=auth(admin_token)).json()
    assert governance not in {group["id"] for group in groups}
    assert submit(client, employee_token, governance).status_code == 201


def test_mover_with_stale_memberships_leaves_employee_unchanged(client, admin_token, test_data, governance):
    employee_id = test_data["employee"].id
    response = client.post(f"/lifecycle/{employee_id}/mover", headers=auth(admin_token), json={
        "department_id": None, "manager_id": None, "job_title": "Changed title",
        "group_ids": [governance], "expected_group_ids": [],
    })
    assert response.status_code == 409
    assert client.get(f"/employees/{employee_id}", headers=auth(admin_token)).json()["job_title"] == test_data["employee"].job_title


@pytest.mark.skipif(test_engine.dialect.name != "postgresql", reason="PostgreSQL advisory locks required")
def test_concurrent_moves_cannot_create_reporting_cycle(client, admin_token, test_data, governance):
    headers = auth(admin_token)
    first_id = test_data["employee"].id
    second = client.post("/lifecycle/joiner", headers=headers, json={
        "employee_number": "CYCLE-CONCURRENT", "first_name": "New", "last_name": "Employee",
        "email": "concurrent@example.com", "job_title": "Analyst", "group_ids": [governance],
    })
    assert second.status_code == 201
    second_id = second.json()["id"]
    barrier = Barrier(2, timeout=5)

    def move(employee_id, manager_id):
        barrier.wait()
        return client.post(f"/lifecycle/{employee_id}/mover", headers=headers, json={
            "department_id": None, "manager_id": manager_id, "job_title": "Analyst",
            "group_ids": [governance],
        }).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [pool.submit(move, first_id, second_id), pool.submit(move, second_id, first_id)]
        assert sorted(future.result(timeout=10) for future in attempts) == [200, 409]
