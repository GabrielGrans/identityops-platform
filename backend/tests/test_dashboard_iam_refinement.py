from datetime import timedelta

from sqlalchemy import select

from backend.app.models.certification import CertificationCampaign, CertificationItem
from backend.app.models.department import Department
from backend.app.models.entra import EntraUser
from backend.app.models.governance import AuditEvent
from backend.app.models.permission import Permission
from backend.app.scripts.seed_permissions import assign_default_permissions
from backend.app.services.department_catalog import department_key, official_code, seed_official_departments
from backend.app.services.entra_access_queue import execute_due
from backend.app.services.entra_automation_tables import changes
from backend.app.services.entra_service import utcnow
from test_unified_entra_directory import (  # noqa: F401
    BASE, GROUP, SECOND, TENANT, USER, headers, integration, migrated, prepare, propose,
)


def platform_role(db, data):
    group = data["admin_group"]
    group.name, group.code = "IT Administrators", "IT_ADMINS"
    db.flush()
    assign_default_permissions(db, group)
    db.commit()


def test_admin_direct_queue_and_verified_graph_execution(
    client, db_session, test_data, admin_token, employee_token, migrated,
):
    graph = prepare(db_session, migrated, test_data)
    platform_role(db_session, test_data)
    admin = headers(admin_token)
    payload = propose(client, admin)
    assert client.post(f"{BASE}/requests", headers=admin, json=payload | {"status": "approved"}).status_code == 422
    response = client.post(f"{BASE}/requests", headers=admin, json=payload)
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["status"] == "direct_authorized" and item["reviewer_id"] is None
    assert item["request"]["direct_authorization"]["actor_id"] == test_data["admin"].id
    assert client.post(f"{BASE}/requests", headers=admin, json=payload).status_code == 409
    assert not graph.writes
    execute_due(db_session, migrated, TENANT, graph.client)
    assert graph.member and len(graph.writes) == 1
    assert db_session.scalar(select(changes.c.status)) == "succeeded"
    event = db_session.scalar(select(AuditEvent).where(AuditEvent.action == "entra.provisioning.direct_authorized"))
    assert event.actor_id == test_data["admin"].id
    assert event.details["reason"] == "platform_administrator_permission"


def test_operator_cannot_spoof_or_inherit_platform_authorization(
    client, db_session, test_data, admin_token, employee_token, migrated,
):
    prepare(db_session, migrated, test_data)
    platform_role(db_session, test_data)
    direct = db_session.scalar(select(Permission).where(Permission.code == "entra:direct_provision"))
    non_admin = test_data["inactive_permission_group"]
    non_admin.permissions.append(db_session.scalar(select(Permission).where(Permission.code == "entra:request_change")))
    db_session.commit()
    assert client.post(f"/groups/{non_admin.id}/permissions/{direct.id}", headers=headers(admin_token)).status_code == 400
    non_admin.permissions.append(direct)  # Simulate an incorrect ACL imported outside the API.
    db_session.commit()
    operator = headers(employee_token)
    payload = propose(client, operator)
    assert client.post(f"{BASE}/requests", headers=operator, json=payload | {"direct_authorization": {
        "actor_id": test_data["admin"].id,
    }}).status_code == 422
    row = client.post(f"{BASE}/requests", headers=operator, json=payload).json()
    assert row["status"] == "pending" and "direct_authorization" not in row["request"]


def test_direct_flow_obeys_write_switch_allowlist_and_live_protection(
    client, db_session, test_data, admin_token, migrated,
):
    graph = prepare(db_session, migrated, test_data)
    platform_role(db_session, test_data)
    admin = headers(admin_token)
    payload = propose(client, admin)
    migrated.ENTRA_WRITE_ENABLED = False
    assert client.post(f"{BASE}/requests", headers=admin, json=payload).status_code == 409
    migrated.ENTRA_WRITE_ENABLED = True
    migrated.ENTRA_WRITE_GROUP_IDS = ""
    assert client.post(f"{BASE}/requests", headers=admin, json=payload).status_code == 409
    migrated.ENTRA_WRITE_GROUP_IDS = GROUP
    migrated.ENTRA_PROTECTED_GROUP_IDS = GROUP
    assert client.post(f"{BASE}/requests", headers=admin, json=payload).status_code == 409
    migrated.ENTRA_PROTECTED_GROUP_IDS = ""
    assert client.post(f"{BASE}/requests", headers=admin, json=payload).status_code == 201
    graph.dynamic = True
    execute_due(db_session, migrated, TENANT, graph.client)
    row = db_session.execute(select(changes)).mappings().one()
    assert row.status == "failed" and row.error_code == "write_unsupported" and not graph.writes


def test_department_seed_normalization_and_dashboard_source_separation(
    client, db_session, test_data, admin_token, migrated,
):
    prepare(db_session, migrated, test_data)
    assert department_key(" ADMINISTRAÇÃO ") == "administracao"
    assert official_code(" administração ") == "ADMINISTRACAO"
    first = set(db_session.scalars(select(Department.id)))
    seed_official_departments(db_session)
    seed_official_departments(db_session)
    db_session.commit()
    assert set(db_session.scalars(select(Department.id))) == first
    user = db_session.scalar(select(EntraUser).where(EntraUser.object_id == USER))
    user.department = " administração "
    user.local_employee_id = test_data["employee"].id
    other = db_session.scalar(select(EntraUser).where(EntraUser.object_id == SECOND))
    other.department = "  "
    db_session.commit()
    auth = headers(admin_token)
    reply = client.get("/departments/operations/catalog", headers=auth)
    assert reply.status_code == 200, reply.text
    assert {row["name"]: row["employees"] for row in reply.json()["entra"]} == {"ADMINISTRAÇÃO": 1, None: 1}
    assert client.post("/departments", headers=auth, json={"name": " administracao ", "code": "ADM-NOVO"}).status_code == 409
    dashboard = client.get("/v1/dashboard/operations", headers=auth)
    assert dashboard.status_code == 200, dashboard.text
    totals = dashboard.json()
    assert totals["local_employees"] == 3 and totals["entra"]["users"] == 2
    assert totals["entra"]["unassigned"] == 1 and totals["official_departments"] == 7
    assert "total_employees" not in totals


def test_operational_certifications_empty_and_completed_progress(
    client, db_session, test_data, admin_token, migrated,
):
    assign_default_permissions(db_session, test_data["admin_group"])
    db_session.commit()
    auth = headers(admin_token)
    path = "/v1/dashboard/operations"
    empty = client.get(path, headers=auth).json()["certification"]
    assert empty["campaigns"] == 0 and empty["completion"] is None
    now = utcnow()
    admin = test_data["admin"]
    employee = test_data["employee"]
    campaign = CertificationCampaign(name="Test review", owner_id=admin.id,
        starts_on=now.date() - timedelta(days=2), due_on=now.date() - timedelta(days=1), status="active")
    db_session.add(campaign)
    db_session.flush()
    db_session.add_all([
        CertificationItem(campaign_id=campaign.id, employee_id=employee.id, group_id=test_data["admin_group"].id,
                          status="revoked", reviewer_id=admin.id, justification="Test revocation", decided_at=now),
        CertificationItem(campaign_id=campaign.id, employee_id=employee.id,
                          group_id=test_data["inactive_permission_group"].id, status="pending"),
    ])
    db_session.commit()
    result = client.get(path, headers=auth).json()["certification"]
    assert result == {"campaigns": 1, "decisions": 1, "completed": 1, "pending": 1,
                      "revoked": 1, "overdue": 1, "completion": 50}


def test_remote_verification_failure_does_not_mark_direct_change_complete(
    client, db_session, test_data, admin_token, migrated,
):
    graph = prepare(db_session, migrated, test_data)
    platform_role(db_session, test_data)
    admin = headers(admin_token)
    response = client.post(f"{BASE}/requests", headers=admin, json=propose(client, admin))
    assert response.status_code == 201
    from backend.app.services.graph_client import GraphClient
    original = GraphClient.has_member

    def unverified(self, group_id, user_id):
        if graph.writes:
            return False
        return original(self, group_id, user_id)

    remote = graph.client()
    remote.has_member = unverified.__get__(remote, GraphClient)
    execute_due(db_session, migrated, TENANT, lambda: remote)
    row = db_session.execute(select(changes)).mappings().one()
    assert graph.writes and row.status == "executing" and row.error_code == "graph_unavailable"
    assert db_session.scalar(select(AuditEvent).where(AuditEvent.action == "entra.provisioning.succeeded")) is None
