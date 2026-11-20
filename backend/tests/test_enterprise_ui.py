from datetime import timedelta

from backend.app.models.governance import AuditEvent
from backend.app.services.entra_automation_tables import alerts, changes
from backend.app.services.entra_service import utcnow
from test_entra import GROUP, USER, headers, integration, migrated  # noqa: F401
from test_entra_automation import grant
from test_graph_client import TENANT


def test_verified_activity_aggregates_once_and_preserves_request_scope(
    client, db_session, migrated, test_data, admin_token, employee_token,
):
    grant(db_session, test_data["admin_group"], "entra:approve_change", "audit:read", "governance:read")
    grant(db_session, test_data["inactive_permission_group"], "entra:request_change")
    actor = test_data["admin"]
    now = utcnow()

    def request_row(status, add, expected, events=()):
        key = db_session.execute(changes.insert().values(
            tenant=TENANT, employee_id=actor.id, requester_id=actor.id,
            user_object_id=USER, group_object_id=GROUP, expires_at=now + timedelta(days=1),
            next_attempt=now, attempts=1, status=status,
            request={"add": add, "expected": expected, "group_id": GROUP, "user_id": USER},
        ).returning(changes.c.id)).scalar_one()
        for action, verified in events:
            db_session.add(AuditEvent(action=f"entra.provisioning.{action}", target_type=changes.name,
                                      target_id=key, created_at=now,
                                      details={"tenant_id": TENANT, "verified_membership": verified}))
        return key

    grant_id = request_row("succeeded", True, False, [("retry", None), ("succeeded", True), ("succeeded", True)])
    request_row("succeeded", False, True, [("succeeded", False)])
    request_row("succeeded", True, True, [("succeeded", True)])
    request_row("succeeded", True, False)
    request_row("direct_authorized", True, False, [("direct_authorized", None)])
    request_row("failed", True, False, [("failed", None)])
    db_session.commit()

    admin, operator = headers(admin_token), headers(employee_token)
    url = "/v1/dashboard/access-activity?days=7"
    assert client.get(url, headers=operator).status_code == 403
    result = client.get(url, headers=admin)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["month"] == {"grants": 1, "revocations": 1}
    assert len(data["series"]) == 7
    assert data["series"][-1] == {"date": now.date().isoformat(), "grants": 1,
                                 "revocations": 1, "succeeded": 3, "failed": 1}
    assert data["groups"][0]["count"] == 2
    timeline = f"/entra/automation/requests/{grant_id}/timeline"
    assert client.get(timeline, headers=operator).status_code == 404
    assert client.get(timeline, headers=admin).json()[0]["verified_membership"] is True
    rows = client.get("/entra/automation/requests?status=failed", headers=admin).json()
    assert len(rows) == 1 and rows[0]["status"] == "failed"

    audit = client.get("/audit-events", headers=admin, params={
        "start_on": now.date().isoformat(), "end_on": now.date().isoformat(),
        "category": "entra_provisioning", "outcome": "failed", "query": "PROVISIONING",
    })
    assert audit.status_code == 200 and len(audit.json()) == 1

    for key, rule in enumerate(("unexpected_access", "privileged_access", "missing_access")):
        db_session.execute(alerts.insert().values(tenant=TENANT, key=str(key), state="unread",
            payload={"rule": rule, "identity": USER, "group_ids": [GROUP], "employee_id": actor.id}))
    db_session.commit()
    distribution = client.get("/v1/dashboard/risk-distribution", headers=admin)
    assert distribution.status_code == 200, distribution.text
    assert distribution.json()["policy_findings"] == 3
    assert distribution.json()["violating_memberships"] == 1
    assert distribution.json()["departments"] == [{"name": test_data["department"].name, "count": 3}]
