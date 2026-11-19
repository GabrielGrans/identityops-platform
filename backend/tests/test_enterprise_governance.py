from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.models.governance import AccessReview, AuditEvent
from backend.app.models.permission import Permission
from test_entra import GROUP, USER, headers, integration, migrated, run_sync, use_snapshot  # noqa: F401


def grant(db, test_data, *actions):
    test_data["admin_group"].permissions.extend(
        Permission(name=f"Governance {action}", code=f"governance:{action}", resource="governance", action=action)
        for action in actions
    )
    db.commit()


def test_policy_authorization_validation_and_audit(client, db_session, test_data, admin_token, employee_token, migrated):
    read = "/governance/policy"
    assert client.get(read, headers=headers(employee_token)).status_code == 403
    assert client.get("/governance/findings", headers=headers(employee_token)).status_code == 403
    grant(db_session, test_data, "read")
    admin = headers(admin_token)
    assert client.get(read, headers=admin).json()["review_max_age_days"] == 30
    assert client.put(read, headers=admin, json={"max_permissions": 2}).status_code == 403
    grant(db_session, test_data, "manage")
    assert client.put(read, headers=admin, json={"privileged_groups": [{"group_id": 999999}]}).status_code == 400
    assert client.put(read, headers=admin, json={"conflicts": [["groups:read", "groups:read"]]}).status_code == 422
    policy = client.put(read, headers=admin, json={"max_permissions": 2, "review_max_age_days": 1})
    assert policy.status_code == 200
    assert client.get(read, headers=admin).json() == policy.json()
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "governance.policy.updated"))
    assert event.details["after"]["max_permissions"] == 2
    assert event.actor_id == test_data["admin"].id


def test_all_findings_use_actual_evidence(client, db_session, test_data, admin_token, migrated, monkeypatch):
    grant(db_session, test_data, "read", "manage")
    admin = headers(admin_token)
    group = test_data["admin_group"]
    inactive = test_data["inactive_employee"]
    inactive.groups.append(group)
    employee = test_data["employee"]
    db_session.add(AccessReview(employee_id=employee.id, group_id=group.id, opened_by=test_data["admin"].id,
                               created_at=datetime.now(timezone.utc) - timedelta(days=3)))
    db_session.commit()
    use_snapshot(monkeypatch)
    assert run_sync(client, admin_token).status_code == 201
    assert client.put(f"/entra/users/{USER}/link", headers=admin, json={"local_id": employee.id}).status_code == 200
    assert client.put(f"/entra/groups/{GROUP}/link", headers=admin, json={"local_id": group.id}).status_code == 200
    assert client.put("/governance/policy", headers=admin, json={
        "max_permissions": 2, "review_max_age_days": 1,
        "privileged_groups": [{"group_id": group.id}],
        "conflicts": [["groups:read", "employees:read"]],
    }).status_code == 200
    report = client.get("/governance/findings", headers=admin).json()
    assert report["counts"] == {
        "entra_mismatch": 1, "excessive_permissions": 1, "inactive_access": 1,
        "overdue_review": 1, "privileged_access": 1, "segregation_of_duties": 1,
    }
    mismatch = next(item for item in report["items"] if item["rule"] == "entra_mismatch")
    assert mismatch["employee_id"] == employee.id
    assert mismatch["evidence"]["entra_only_group_ids"] == [group.id]
    assert report["entra_state"] == "evaluated"
    page = client.get("/governance/findings?limit=1&offset=1", headers=admin).json()
    assert page["total"] == 6 and page["items"] == report["items"][1:2]
    details = client.get(f"/entra/users/{USER}/access", headers=admin).json()
    assert details["groups"][0]["object_id"] == GROUP
    assert details["comparison"]["entra_only_group_ids"] == [group.id]


def test_stale_and_unauthorized_entra_data_is_not_compared(
    client, db_session, test_data, admin_token, migrated, monkeypatch,
):
    from backend.app.models.entra import EntraSyncRun

    grant(db_session, test_data, "read")
    admin = headers(admin_token)
    use_snapshot(monkeypatch)
    assert run_sync(client, admin_token).status_code == 201
    report = client.get("/governance/findings", headers=admin).json()
    assert report["entra_state"] == "evaluated"
    run = db_session.scalar(select(EntraSyncRun))
    run.finished_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()
    report = client.get("/governance/findings", headers=admin).json()
    assert report["entra_state"] == "unavailable"
    assert "entra_mismatch" not in report["evaluated_rules"]
    assert client.get(f"/entra/users/{USER}/access", headers=admin).json()["comparison"] is None

    run.finished_at = datetime.now(timezone.utc)
    group = test_data["admin_group"]
    group.permissions.remove(next(permission for permission in group.permissions if permission.code == "entra:read"))
    db_session.commit()
    assert client.get(f"/entra/users/{USER}/access", headers=admin).status_code == 403
    assert client.get("/governance/findings", headers=admin).json()["entra_state"] == "unavailable"
