from datetime import timedelta
from uuid import UUID

import httpx
from sqlalchemy import select

from backend.app.models.entra import EntraSyncRun, EntraUser
from backend.app.models.governance import AuditEvent
from backend.app.models.permission import Permission
from backend.app.services.entra_access_queue import execute_due
from backend.app.services.entra_automation_tables import changes, state
from backend.app.services.entra_role_governance import refresh_alerts
from backend.app.services.entra_service import utcnow
from backend.app.services.entra_sync_worker import sync_due
from backend.app.services.graph_client import GraphClient, GraphConfig, TokenCache
from test_entra import GROUP, USER, headers, integration, migrated  # noqa: F401
from test_graph_client import TENANT

BASE = "/entra/automation"
GRAPH = "https://graph.microsoft.com/v1.0"
SECOND = str(UUID(int=500))


class GraphFixture:
    incremental = False
    throttle = False
    member = False
    dynamic = False

    def __init__(self, settings):
        self.config = GraphConfig.from_settings(settings)
        self.http = httpx.Client(transport=httpx.MockTransport(self.dispatch))
        self.cache = TokenCache()
        self.writes = []

    def client(self):
        return GraphClient(self.config, self.http, self.cache)

    def dispatch(self, request):
        path = request.url.path
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600, "token_type": "Bearer"})
        if self.throttle:
            return httpx.Response(429, headers={"Retry-After": "120"})
        if path.endswith("/delta"):
            users = "/users/" in path
            if self.incremental:
                assert request.url.params["$deltatoken"] == "checkpoint"
                records = ([{"id": USER, "jobTitle": "Engineer"}, {"id": SECOND, "@removed": {}}]
                           if users else [])
            else:
                records = ([{"id": USER, "accountEnabled": True, "mail": "worker@example.com", "jobTitle": "Analyst"},
                            {"id": SECOND, "accountEnabled": True}] if users else
                           [{"id": GROUP, "displayName": "Test security group", "securityEnabled": True,
                             "mailEnabled": False, "groupTypes": [], "onPremisesSyncEnabled": None,
                             "isAssignableToRole": False}])
            return httpx.Response(200, json={"value": records,
                "@odata.deltaLink": f"{GRAPH}/{'users' if users else 'groups'}/delta?$deltatoken=checkpoint"})
        if path.endswith("/members"):
            return httpx.Response(200, json={"value": [{"id": USER, "@odata.type": "#microsoft.graph.user"}] if self.member else []})
        if path.endswith(f"/groups/{GROUP}"):
            return httpx.Response(200, json={"id": GROUP, "securityEnabled": True, "mailEnabled": False,
                "groupTypes": ["DynamicMembership"] if self.dynamic else [], "onPremisesSyncEnabled": None,
                "isAssignableToRole": False})
        if path.endswith("/$ref"):
            self.writes.append((request.method, path))
            self.member = request.method == "POST"
            return httpx.Response(204)
        if path.endswith(f"/members/{USER}"):
            return httpx.Response(200 if self.member else 404)
        raise AssertionError(path)


def grant(db, group, *codes):
    for code in codes:
        resource, action = code.split(":")
        group.permissions.append(Permission(code=code, name=code, resource=resource, action=action))
    db.commit()


def make_due(db):
    db.execute(state.update().values(next_run=utcnow() - timedelta(seconds=1)))
    db.commit()


def test_durable_checkpoints_tombstones_and_throttle(db_session, migrated):
    graph = GraphFixture(migrated)
    sync_due(db_session, TENANT, 10, graph.client)
    first = db_session.execute(select(state)).mappings().one()
    assert first.checkpoint["users"].endswith("checkpoint")
    assert db_session.scalar(select(EntraSyncRun)).actor_id is None
    graph.incremental = True
    make_due(db_session)
    sync_due(db_session, TENANT, 10, graph.client)
    user = db_session.scalar(select(EntraUser).where(EntraUser.object_id == USER))
    second = db_session.scalar(select(EntraUser).where(EntraUser.object_id == SECOND))
    assert user.job_title == "Engineer" and user.mail == "worker@example.com"
    assert second.present is False
    make_due(db_session)
    graph.throttle = True
    sync_due(db_session, TENANT, 10, graph.client)
    status = db_session.execute(select(state)).mappings().one()
    assert status.failures == 1
    assert status.checkpoint["run_id"] > first.checkpoint["run_id"]
    assert status.next_run > utcnow() + timedelta(seconds=110)
    assert user.present is True
    assert not graph.writes


def test_two_person_approval_verified_writeback_and_deduplicated_alerts(
    client, db_session, migrated, admin_token, employee_token, test_data,
):
    graph = GraphFixture(migrated)
    migrated.ENTRA_WRITE_ENABLED = True
    migrated.ENTRA_WRITE_GROUP_IDS = GROUP
    grant(db_session, test_data["admin_group"], "entra:request_change", "governance:read", "governance:manage")
    grant(db_session, test_data["inactive_permission_group"], "entra:approve_change")
    sync_due(db_session, TENANT, 10, graph.client)
    admin, reviewer = headers(admin_token), headers(employee_token)
    subject = test_data["inactive_employee"]
    subject.status = "active"
    db_session.commit()
    assert client.put(f"/entra/users/{USER}/link", headers=admin, json={"local_id": subject.id}).status_code == 200
    data = {"employee_id": subject.id, "group_id": GROUP, "add": True, "justification": "Required for testing"}
    preview = client.post(f"{BASE}/preview", headers=admin, json=data)
    assert preview.status_code == 200, preview.text
    response = client.post(f"{BASE}/requests", headers=admin,
                           json=data | {"expected_snapshot_id": preview.json()["snapshot_id"]})
    assert response.status_code == 201, response.text
    row_id = response.json()["id"]
    decision = f"{BASE}/requests/{row_id}/decision"
    assert client.post(decision, headers=admin, json={"approve": True, "note": "Looks good"}).status_code == 403
    execute_due(db_session, migrated, TENANT, graph.client)
    assert not graph.writes
    assert client.post(decision, headers=reviewer, json={"approve": True, "note": "Looks good"}).status_code == 200
    graph.throttle = True
    execute_due(db_session, migrated, TENANT, graph.client)
    row = db_session.execute(select(changes)).mappings().one()
    assert row.status == "approved" and row.attempts == 1
    assert row.next_attempt > utcnow() + timedelta(seconds=110)
    graph.throttle = False
    db_session.execute(changes.update().values(next_attempt=utcnow() - timedelta(seconds=1)))
    db_session.commit()
    execute_due(db_session, migrated, TENANT, graph.client)
    execute_due(db_session, migrated, TENANT, graph.client)
    assert graph.member and graph.writes == [("POST", f"/v1.0/groups/{GROUP}/members/$ref")]
    assert db_session.scalar(select(changes.c.status)) == "succeeded"
    assert db_session.scalar(select(AuditEvent).where(AuditEvent.action == "entra.provisioning.succeeded"))
    graph.incremental = True
    make_due(db_session)
    sync_due(db_session, TENANT, 10, graph.client)
    policy = {"roles": [{"name": "Engineering", "job_title": "Engineer", "approved": []}]}
    assert client.put(f"{BASE}/role-policy", headers=admin, json=policy).status_code == 200
    refresh_alerts(db_session, TENANT)
    refresh_alerts(db_session, TENANT)
    alerts = client.get(f"{BASE}/notifications", headers=admin).json()
    assert len(alerts) == 1 and alerts[0]["payload"]["rule"] == "unexpected_access"
    assert client.put(f"{BASE}/notifications/{alerts[0]['key']}", headers=admin).json()["acknowledged"]
    refresh_alerts(db_session, TENANT)
    assert client.get(f"{BASE}/notifications?unread=true", headers=admin).json() == []


def test_graph_blocks_unsupported_groups_and_deletes_only_reference(migrated):
    graph = GraphFixture(migrated)
    from backend.app.services.graph_client import GraphError
    import pytest

    graph.dynamic = True
    with pytest.raises(GraphError, match="does not support"):
        graph.client().check_group(GROUP)
    assert not graph.writes
    graph.dynamic = False
    graph.member = True
    client = graph.client()
    client.check_group(GROUP)
    client.change_member(GROUP, USER, False)
    assert graph.writes == [("DELETE", f"/v1.0/groups/{GROUP}/members/{USER}/$ref")]
    assert client.has_member(GROUP, USER) is False
