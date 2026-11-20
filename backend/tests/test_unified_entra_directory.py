from datetime import timedelta

import pytest
from backend.app.models.entra import EntraGroup, EntraSyncRun, EntraUser
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


def test_read_only_preview_does_not_authorize_execution(
    client, db_session, test_data, admin_token, employee_token, migrated,
):
    graph = prepare(db_session, migrated, test_data)
    migrated.ENTRA_WRITE_ENABLED = False
    migrated.ENTRA_WRITE_GROUP_IDS = ""
    admin = headers(admin_token)
    data = {"user_id": USER, "group_id": GROUP, "add": True, "justification": "Read-only preview for the fixture"}
    assert client.post(f"{BASE}/preview", headers=headers(employee_token), json=data).status_code == 403
    response = client.post(f"{BASE}/preview", headers=admin, json=data)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["can_submit"] is False and result["write_blocker"] == "write_disabled"
    assert result["direct_authorized"] is False
    groups = client.get(f"{DIRECTORY}/groups?classification=eligible&limit=1", headers=admin).json()
    assert groups["items"][0]["object_id"] == GROUP
    assert groups["items"][0]["write_blocker"] == "write_disabled"
    assert not client.get(f"{DIRECTORY}/groups?classification=protected", headers=admin).json()["items"]

    confirmation = data | {"expected_snapshot_id": result["snapshot_id"]}
    disabled = client.post(f"{BASE}/requests", headers=admin, json=confirmation)
    assert disabled.status_code == 409 and "disabled" in disabled.json()["detail"]
    migrated.ENTRA_WRITE_ENABLED = True  # Only the in-memory configuration for this mocked test.
    assert client.post(f"{BASE}/preview", headers=admin, json=data).json()["write_blocker"] == "group_not_allowlisted"
    assert client.post(f"{BASE}/requests", headers=admin, json=confirmation).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(changes)) == 0
    assert not graph.writes


@pytest.mark.parametrize("field,value,classification", [
    ("role_assignable", True, "protected"),
    ("group_types", ["DynamicMembership"], "unsupported"),
    ("on_premises_sync_enabled", True, "unsupported"),
    ("management_metadata_complete", False, "unsupported"),
])
def test_preview_rejects_group_for_remote_and_employee_selectors(
    client, db_session, test_data, admin_token, migrated, field, value, classification,
):
    graph = prepare(db_session, migrated, test_data)
    group = db_session.scalar(select(EntraGroup).where(EntraGroup.object_id == GROUP))
    user = db_session.scalar(select(EntraUser).where(EntraUser.object_id == USER))
    setattr(group, field, value)
    user.local_employee_id = test_data["admin"].id
    db_session.commit()
    admin = headers(admin_token)
    for subject in ({"user_id": USER}, {"employee_id": user.local_employee_id}):
        response = client.post(f"{BASE}/preview", headers=admin, json=subject | {
            "group_id": GROUP, "add": True, "justification": "Unsafe group fixture",
        })
        assert response.status_code == 409
    matching = client.get(f"{DIRECTORY}/groups?classification={classification}", headers=admin).json()
    assert matching["items"][0]["object_id"] == GROUP
    assert not graph.writes


def test_preview_rejects_stale_snapshot(client, db_session, test_data, admin_token, migrated):
    graph = prepare(db_session, migrated, test_data)
    run = db_session.scalar(select(EntraSyncRun).where(EntraSyncRun.status == "completed"))
    run.finished_at = utcnow() - timedelta(days=10)
    db_session.commit()
    response = client.post(f"{BASE}/preview", headers=headers(admin_token), json={
        "user_id": USER, "group_id": GROUP, "add": False, "justification": "Stale snapshot fixture",
    })
    assert response.status_code == 409 and "Synchronize" in response.json()["detail"]
    assert not graph.writes


def test_approval_and_worker_recheck_write_policy_after_preview(
    client, db_session, test_data, admin_token, employee_token, migrated,
):
    graph = prepare(db_session, migrated, test_data)
    admin, reviewer = headers(admin_token), headers(employee_token)
    confirmed = propose(client, admin)
    created = client.post(f"{BASE}/requests", headers=admin, json=confirmed)
    assert created.status_code == 201
    decision = f"{BASE}/requests/{created.json()['id']}/decision"
    body = {"approve": True, "note": "Reviewed externally"}
    migrated.ENTRA_WRITE_ENABLED = False
    assert client.post(decision, headers=reviewer, json=body).status_code == 409
    migrated.ENTRA_WRITE_ENABLED = True
    assert client.post(decision, headers=reviewer, json=body).status_code == 200
    migrated.ENTRA_WRITE_GROUP_IDS = ""
    execute_due(db_session, migrated, TENANT, graph.client)
    status, reason = db_session.execute(select(changes.c.status, changes.c.error_code)).one()
    assert (status, reason) == ("failed", "group_not_allowlisted")
    assert not graph.writes


def test_preview_prefixes_are_registered_in_fastapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in (f"{BASE}/preview", "/integrations/servicenow/access-requests/preview"):
        assert "post" in paths[path]
        assert f"/api{path}" not in paths  # The reverse proxy strips its external /api prefix.


@pytest.mark.parametrize("mode", ["manual", "worker"])
@pytest.mark.parametrize("detail_complete", [True, False])
def test_sync_backfills_metadata_and_preview_fails_closed(
    client, db_session, test_data, admin_token, migrated, monkeypatch, mode, detail_complete,
):
    from backend.app.api.routes.entra import snapshot_loader

    class PartialGraph(GraphFixture):
        detail_calls = 0

        def dispatch(self, request):
            path = request.url.path
            if path == "/v1.0/users":
                return httpx.Response(200, json={"value": [{"id": USER, "accountEnabled": True}]})
            if path in ("/v1.0/groups", "/v1.0/groups/delta"):
                assert {"securityEnabled", "mailEnabled", "groupTypes", "onPremisesSyncEnabled",
                        "isAssignableToRole"} <= set(request.url.params["$select"].split(","))
                value = {"value": [{"id": GROUP, "securityEnabled": True, "mailEnabled": False}]}
                if path.endswith("/delta"):
                    value["@odata.deltaLink"] = "https://graph.microsoft.com/v1.0/groups/delta?$deltatoken=fixture"
                return httpx.Response(200, json=value)
            if path == f"/v1.0/groups/{GROUP}":
                self.detail_calls += 1
                metadata = {"id": GROUP, "mailEnabled": False, "onPremisesSyncEnabled": None}
                if detail_complete:
                    metadata.update(securityEnabled=True, isAssignableToRole=False, groupTypes=[])
                return httpx.Response(200, json=metadata)
            return super().dispatch(request)

    graph = PartialGraph(migrated)
    grant(db_session, test_data["admin_group"], "entra:request_change")
    assert not migrated.ENTRA_WRITE_ENABLED and not migrated.ENTRA_WRITE_GROUP_IDS
    admin = headers(admin_token)
    if mode == "manual":
        monkeypatch.setitem(client.app.dependency_overrides, snapshot_loader, lambda: lambda _: graph.client().snapshot())
        response = client.post("/entra/sync", headers=admin)
        assert response.status_code == 201, response.text
    else:
        assert sync_due(db_session, TENANT, 10, graph.client) is True
    assert graph.detail_calls == 1
    group = db_session.scalar(select(EntraGroup).where(EntraGroup.object_id == GROUP))
    assert group.security_enabled is True
    assert group.management_metadata_complete is detail_complete
    assert group.role_assignable is (False if detail_complete else None)
    assert group.group_types == ([] if detail_complete else None)
    assert group.on_premises_sync_enabled is None
    result = client.post(f"{BASE}/preview", headers=admin, json={
        "user_id": USER, "group_id": GROUP, "add": True, "justification": "Validate Graph metadata fixture",
    })
    assert result.status_code == (200 if detail_complete else 409), result.text
    if detail_complete:
        assert result.json()["can_submit"] is False
    assert not graph.writes
