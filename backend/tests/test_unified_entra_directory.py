from datetime import timedelta

import httpx
from sqlalchemy import func, select

from backend.app.models.associations import employee_groups
from backend.app.models.employee import Employee
from backend.app.services.entra_access_queue import execute_due
from backend.app.services.entra_automation_tables import changes, state
from backend.app.services.entra_role_governance import refresh_alerts
from backend.app.services.entra_service import utcnow
from backend.app.services.entra_sync_worker import sync_due
from test_entra_automation import (  # noqa: F401
    BASE, GROUP, SECOND, TENANT, USER, GraphFixture, grant, headers, integration, migrated,
)

DIRECTORY = "/entra/directory"


class UnifiedGraphFixture(GraphFixture):
    def dispatch(self, request):
        response = super().dispatch(request)
        if request.url.path.endswith("/delta") and response.status_code == 200:
            payload = response.json()
            for row in payload["value"]:
                if "/groups/" in request.url.path:
                    row.update(description="Engineering access", groupTypes=[], mailEnabled=False,
                               isAssignableToRole=False, onPremisesSyncEnabled=None)
                elif row["id"] == USER:
                    row.update(displayName="Fixture Analyst", department="Engineering", onPremisesSyncEnabled=True)
            return httpx.Response(200, json=payload)
        return response


def prepare(db, config, data):
    graph = UnifiedGraphFixture(config)
    config.ENTRA_WRITE_ENABLED = True
    config.ENTRA_WRITE_GROUP_IDS = GROUP
    grant(db, data["admin_group"], "entra:request_change", "governance:read", "governance:manage")
    grant(db, data["inactive_permission_group"], "entra:approve_change")
    sync_due(db, TENANT, 10, graph.client)
    return graph


def propose(client, auth, user_id=USER, add=True):
    draft = {"user_id": user_id, "group_id": GROUP, "add": add, "justification": "Needed for onboarding"}
    response = client.post(f"{BASE}/preview", headers=auth, json=draft)
    assert response.status_code == 200, response.text
    return draft | {"expected_snapshot_id": response.json()["snapshot_id"]}


def test_unified_sources_search_pagination_and_isolation(
    client, db_session, test_data, admin_token, employee_token, migrated,
):
    prepare(db_session, migrated, test_data)
    admin = headers(admin_token)
    assert client.get(f"{DIRECTORY}/users", headers=headers(employee_token)).status_code == 403
    page = client.get(f"{DIRECTORY}/users?limit=1", headers=admin).json()
    assert page["items"][0]["source"] == "entra"
    assert page["next_after"] is not None
    next_page = client.get(f"{DIRECTORY}/users?limit=1&after={page['next_after']}", headers=admin).json()
    assert next_page["items"][0]["object_id"] != page["items"][0]["object_id"]
    for match in ("engineering", "analyst", "worker@example.com"):
        result = client.get(f"{DIRECTORY}/users", headers=admin, params={"query": match}).json()
        assert [row["object_id"] for row in result["items"]] == [USER]
        assert result["items"][0]["profile_authority"] == "external"
        assert result["items"][0]["profile_write_supported"] is False
    result = client.get(f"{DIRECTORY}/groups?query=Engineering", headers=admin).json()["items"][0]
    assert result["source"] == "entra" and result["description"] == "Engineering access"
    assert result["eligibility"] == "eligible" and result["membership_count"] == 0
    migrated.ENTRA_PROTECTED_GROUP_IDS = GROUP
    group = client.get(f"{DIRECTORY}/groups/{GROUP}", headers=admin).json()
    assert group["eligibility"] == "protected"
    assert client.post(f"{BASE}/preview", headers=admin, json={
        "user_id": USER, "group_id": GROUP, "add": True, "justification": "Should be denied",
    }).status_code == 409
    assert len(client.get("/employees", headers=admin).json()) == 3
    assert all(row["name"] != "Test security group" for row in client.get("/groups", headers=admin).json())


def test_remote_subject_approval_refresh_and_expired_exception(
    client, db_session, test_data, admin_token, employee_token, migrated,
):
    graph = prepare(db_session, migrated, test_data)
    admin, reviewer = headers(admin_token), headers(employee_token)
    before = db_session.scalar(select(func.count()).select_from(employee_groups))
    payload = propose(client, admin)
    bad = client.post(f"{BASE}/requests", headers=admin, json=payload | {"expected_snapshot_id": 999999})
    assert bad.status_code == 409
    created = client.post(f"{BASE}/requests", headers=admin, json=payload)
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["employee_id"] is None and row["user_object_id"] == USER
    assert client.post(f"{BASE}/requests", headers=admin, json=payload).status_code == 409
    action = f"{BASE}/requests/{row['id']}/decision"
    assert client.post(action, headers=admin, json={"approve": True, "note": "Self approval blocked"}).status_code == 403
    assert client.post(action, headers=reviewer, json={"approve": True, "note": "Reviewed externally"}).status_code == 200
    execute_due(db_session, migrated, TENANT, graph.client)
    assert db_session.scalar(select(changes.c.status)) == "succeeded" and graph.member
    assert db_session.scalar(select(state.c.next_run)) <= utcnow()
    sync_due(db_session, TENANT, 10, graph.client)
    groups = client.get(f"{DIRECTORY}/users/{USER}", headers=admin).json()["groups"]
    assert [group["object_id"] for group in groups] == [GROUP]
    members = client.get(f"{DIRECTORY}/groups/{GROUP}", headers=admin).json()["members"]
    assert [user["object_id"] for user in members["items"]] == [USER]
    assert db_session.scalar(select(func.count()).select_from(employee_groups)) == before
    assert db_session.scalar(select(func.count()).select_from(Employee)) == 3
    assert client.put(f"{BASE}/role-policy", headers=admin, json={
        "roles": [{"name": "Engineering", "entra_department": "engineering", "exceptions": [
            {"user_id": USER, "group_id": GROUP, "until": (utcnow().date() - timedelta(days=1)).isoformat()},
        ]}],
    }).status_code == 200
    refresh_alerts(db_session, TENANT)
    findings = client.get(f"{DIRECTORY}/users/{USER}", headers=admin).json()["findings"]
    assert {item["payload"]["rule"] for item in findings} == {"expired_exception", "unexpected_access"}
    assert all(item["payload"]["group_ids"] == [GROUP] for item in findings)


def test_writeback_failure_and_stale_approval(client, db_session, test_data, admin_token, employee_token, migrated):
    graph = prepare(db_session, migrated, test_data)
    admin, reviewer = headers(admin_token), headers(employee_token)
    row = client.post(f"{BASE}/requests", headers=admin, json=propose(client, admin)).json()
    action = f"{BASE}/requests/{row['id']}/decision"
    assert client.post(action, headers=reviewer, json={"approve": True, "note": "Reviewed externally"}).status_code == 200
    graph.dynamic = True
    execute_due(db_session, migrated, TENANT, graph.client)
    assert not graph.writes
    failed = client.get(f"{BASE}/requests", headers=admin).json()[0]
    assert failed["status"] == "failed" and failed["error_code"] == "write_unsupported"
    row = client.post(f"{BASE}/requests", headers=admin, json=propose(client, admin, SECOND)).json()
    db_session.execute(changes.update().where(changes.c.id == row["id"]).values(expires_at=utcnow() - timedelta(seconds=1)))
    db_session.commit()
    assert client.post(f"{BASE}/requests/{row['id']}/decision", headers=reviewer,
                       json={"approve": True, "note": "Expired approval"}).status_code == 409
