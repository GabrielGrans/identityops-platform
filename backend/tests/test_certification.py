from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.models.associations import employee_groups
from backend.app.models.certification import CertificationBase, CertificationItem
from backend.app.models.entra import EntraBase
from backend.app.models.governance import AuditEvent
from backend.app.models.permission import Permission
from backend.app.scripts.migrate import upgrade_database
from backend.app.services import certification_service


URL = "/certification-campaigns"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def cleanup(bind):
    with bind.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("DROP TRIGGER IF EXISTS identityops_certification_membership_removed ON employee_groups"))
            connection.execute(text("DROP FUNCTION IF EXISTS identityops_supersede_certification_items()"))
        else:
            connection.execute(text("DROP TRIGGER IF EXISTS identityops_certification_membership_removed"))
        connection.execute(text("DROP TABLE IF EXISTS enterprise_governance_policy"))
        CertificationBase.metadata.drop_all(connection)
        EntraBase.metadata.drop_all(connection)
        connection.execute(text("DROP TABLE IF EXISTS identityops_schema_version"))


@pytest.fixture
def roles(db_session, test_data):
    manage = Permission(name="Manage Certifications", code="certifications:manage", resource="certifications", action="manage")
    review = Permission(name="Review Certifications", code="certifications:review", resource="certifications", action="review")
    test_data["admin_group"].permissions.extend([manage, review])
    test_data["inactive_permission_group"].permissions.append(review)
    test_data["inactive_permission_group"].permissions.append(test_data["permissions"]["employees:read"])
    db_session.commit()
    return test_data


@pytest.fixture
def schema(db_session, roles):
    bind = db_session.get_bind()
    upgrade_database(bind, revision="certification_090")
    try:
        yield roles
    finally:
        db_session.rollback()
        cleanup(bind)


def campaign_data(roles, **changes):
    today = datetime.now(timezone.utc).date()
    return {
        "name": "Quarterly certification",
        "description": "Review active access",
        "owner_id": roles["admin"].id,
        "starts_on": str(today),
        "due_on": str(today + timedelta(days=5)),
        "reviewer_ids": [roles["admin"].id, roles["employee"].id],
    } | changes


def create(client, token, roles, **changes):
    response = client.post(URL, headers=auth(token), json=campaign_data(roles, **changes))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def transition(client, token, campaign_id, action):
    return client.post(f"{URL}/{campaign_id}/transition", headers=auth(token), json={"action": action})


def get_items(client, token, campaign_id):
    response = client.get(f"{URL}/{campaign_id}/items", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def decide(client, token, campaign_id, item_id, decision="retained", justification="Business need confirmed"):
    return client.post(f"{URL}/{campaign_id}/items/{item_id}/decision", headers=auth(token),
                       json={"decision": decision, "justification": justification})


def test_additive_migration_from_v080(client, admin_token, db_session, roles):
    bind = db_session.get_bind()
    upgrade_database(bind, revision="entra_080")
    try:
        before = set(inspect(bind).get_table_names())
        assert "entra_users" in before and "certification_items" not in before
        assert client.get(URL, headers=auth(admin_token)).status_code == 503
        count_before = len(db_session.execute(select(employee_groups)).all())
        db_session.commit()
        upgrade_database(bind, revision="certification_090")
        upgrade_database(bind, revision="certification_090")
        assert set(inspect(bind).get_table_names()) - before == {
            "certification_campaigns", "certification_reviewers", "certification_items",
        }
        assert db_session.scalar(text("SELECT version_num FROM identityops_schema_version")) == "certification_090"
        assert len(db_session.execute(select(employee_groups)).all()) == count_before
        assert client.get(URL, headers=auth(admin_token)).json() == []
    finally:
        db_session.rollback()
        cleanup(bind)


def test_lifecycle_snapshot_retain_revoke_and_audit(client, db_session, admin_token, employee_token, schema):
    campaign = create(client, admin_token, schema)
    assert get_items(client, admin_token, campaign) == []
    assert transition(client, admin_token, campaign, "complete").status_code == 409
    assert transition(client, admin_token, campaign, "activate").json()["status"] == "active"
    assert transition(client, admin_token, campaign, "activate").status_code == 409
    items = get_items(client, admin_token, campaign)
    assert len(items) == 2  # Inactive groups and employees are excluded.
    subject = next(item for item in items if item["employee_id"] == schema["employee"].id)
    admin = next(item for item in items if item["employee_id"] == schema["admin"].id)
    assert transition(client, admin_token, campaign, "complete").status_code == 409
    assert decide(client, employee_token, campaign, subject["id"], "revoked").status_code == 403
    assert decide(client, admin_token, campaign, subject["id"], justification="  ").status_code == 422
    retained = decide(client, employee_token, campaign, admin["id"])
    assert retained.json()["status"] == "retained"
    assert retained.json()["reviewer_id"] == schema["employee"].id
    result = decide(client, admin_token, campaign, subject["id"], "revoked")
    assert result.status_code == 200, result.text
    assert result.json()["justification"] == "Business need confirmed"
    assert result.json()["decided_at"]
    assert decide(client, admin_token, campaign, subject["id"]).status_code == 409
    assert db_session.execute(select(employee_groups).where(
        employee_groups.c.employee_id == subject["employee_id"], employee_groups.c.group_id == subject["group_id"],
    )).first() is None
    assert transition(client, admin_token, campaign, "complete").json()["status"] == "completed"
    detail = client.get(f"{URL}/{campaign}", headers=auth(admin_token)).json()
    assert detail["counts"] == {"retained": 1, "revoked": 1}
    assert detail["available_actions"] == []
    assert transition(client, admin_token, campaign, "cancel").status_code == 409
    audit = db_session.scalars(select(AuditEvent.action).where(AuditEvent.action.like("certification.%")).order_by(AuditEvent.id)).all()
    assert audit == ["certification.created", "certification.activated", "certification.item_retained",
                     "certification.item_revoked", "certification.completed"]


def test_permissions_assignment_scope_and_input_validation(client, admin_token, employee_token, inactive_employee_token, schema):
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=auth(inactive_employee_token)).status_code == 401
    assert client.post(URL, headers=auth(employee_token), json=campaign_data(schema)).status_code == 403
    bad = campaign_data(schema, reviewer_ids=[schema["inactive_employee"].id])
    assert client.post(URL, headers=auth(admin_token), json=bad).status_code == 422
    duplicate = campaign_data(schema, reviewer_ids=[schema["admin"].id] * 2)
    assert client.post(URL, headers=auth(admin_token), json=duplicate).status_code == 422
    invalid = campaign_data(schema, starts_on="2030-01-01", due_on="2029-01-01")
    assert client.post(URL, headers=auth(admin_token), json=invalid).status_code == 422

    private = create(client, admin_token, schema, reviewer_ids=[schema["admin"].id])
    visible = create(client, admin_token, schema)
    assert [row["id"] for row in client.get(URL, headers=auth(employee_token)).json()] == [visible]
    assert client.get(f"{URL}/{private}", headers=auth(employee_token)).status_code == 404
    assert client.get(f"{URL}/{private}/items", headers=auth(employee_token)).status_code == 404
    assert transition(client, employee_token, visible, "activate").status_code == 403
    assert transition(client, admin_token, private, "activate").status_code == 200
    items = get_items(client, admin_token, private)
    assert decide(client, employee_token, private, items[0]["id"]).status_code == 404
    assert decide(client, admin_token, visible, items[0]["id"]).status_code == 404
    endpoint = f"{URL}/{private}/reviewers"
    replacement = {"reviewer_ids": [schema["employee"].id]}
    assert client.put(endpoint, headers=auth(employee_token), json=replacement).status_code == 403
    assert client.put(endpoint, headers=auth(admin_token), json=replacement).status_code == 200
    item = next(item for item in items if item["employee_id"] == schema["admin"].id)
    assert decide(client, employee_token, private, item["id"]).status_code == 200


def test_removal_and_regrant_does_not_revive_snapshot(client, admin_token, schema):
    first = create(client, admin_token, schema)
    second = create(client, admin_token, schema)
    for campaign in (first, second):
        assert transition(client, admin_token, campaign, "activate").status_code == 200
    def employee_item(campaign):
        return next(item for item in get_items(client, admin_token, campaign) if item["employee_id"] == schema["employee"].id)

    item = employee_item(first)
    assert decide(client, admin_token, first, item["id"], "revoked").json()["status"] == "revoked"
    assert employee_item(second)["status"] == "superseded"
    path = f"/employees/{item['employee_id']}/groups/{item['group_id']}"
    assert client.post(path, headers=auth(admin_token)).status_code == 200
    blocked = decide(client, admin_token, second, employee_item(second)["id"], "revoked")
    assert blocked.status_code == 409
    assert employee_item(second)["status"] == "superseded"


def test_dates_expiration_and_cancellation_never_revoke_memberships(client, db_session, admin_token, schema, monkeypatch):
    today = certification_service.utcnow()
    future = (today + timedelta(days=1)).date().isoformat()
    campaign = create(client, admin_token, schema, starts_on=future, due_on=future)
    cancelled = create(client, admin_token, schema)
    assert transition(client, admin_token, campaign, "activate").status_code == 409
    assert transition(client, admin_token, cancelled, "activate").status_code == 200
    assert transition(client, admin_token, cancelled, "cancel").json()["status"] == "cancelled"
    assert {row["status"] for row in get_items(client, admin_token, cancelled)} == {"not_reviewed"}
    count = len(db_session.execute(select(employee_groups)).all())
    db_session.commit()
    monkeypatch.setattr(certification_service, "utcnow", lambda: today + timedelta(days=1))
    assert transition(client, admin_token, campaign, "activate").status_code == 200
    assert transition(client, admin_token, campaign, "expire").status_code == 409
    monkeypatch.setattr(certification_service, "utcnow", lambda: today + timedelta(days=2))
    item = next(row for row in get_items(client, admin_token, campaign) if row["employee_id"] == schema["employee"].id)
    assert decide(client, admin_token, campaign, item["id"], "revoked").status_code == 409
    assert transition(client, admin_token, campaign, "expire").json()["status"] == "expired"
    assert {row["status"] for row in get_items(client, admin_token, campaign)} == {"not_reviewed"}
    assert len(db_session.execute(select(employee_groups)).all()) == count


def test_database_rejects_duplicate_membership_item(client, db_session, admin_token, schema):
    campaign = create(client, admin_token, schema)
    assert transition(client, admin_token, campaign, "activate").status_code == 200
    item = get_items(client, admin_token, campaign)[0]
    db_session.add(CertificationItem(campaign_id=campaign, employee_id=item["employee_id"],
                                     group_id=item["group_id"], status="pending"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_concurrent_decisions_commit_once_on_postgresql(client, db_session, admin_token, schema):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("Independent connections and PostgreSQL row locks required")
    campaign = create(client, admin_token, schema)
    assert transition(client, admin_token, campaign, "activate").status_code == 200
    item = next(row for row in get_items(client, admin_token, campaign) if row["employee_id"] == schema["employee"].id)
    barrier = Barrier(2)

    def run():
        barrier.wait(timeout=5)
        return decide(client, admin_token, campaign, item["id"], "revoked").status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        one, two = workers.submit(run), workers.submit(run)
        assert sorted([one.result(timeout=10), two.result(timeout=10)]) == [200, 409]
