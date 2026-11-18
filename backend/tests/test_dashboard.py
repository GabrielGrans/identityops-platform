from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from backend.app.models.certification import CertificationCampaign, CertificationItem
from backend.app.models.governance import AccessRequest, AccessReview, AuditEvent
from backend.app.models.group import Group
from backend.app.models.permission import Permission
from backend.app.scripts.migrate import upgrade_database
from backend.app.services import dashboard_service
from test_certification import cleanup


SUMMARY = "/v1/dashboard/summary"
ACTIVITY = "/v1/dashboard/activity"
NOW = datetime(2026, 7, 10, 14, tzinfo=timezone.utc)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def freeze_dashboard(monkeypatch):
    monkeypatch.setattr(dashboard_service, "utcnow", lambda: NOW)


@pytest.fixture
def full_access(db_session, test_data):
    for resource, action in (("audit", "read"), ("reviews", "manage"), ("certifications", "manage")):
        test_data["admin_group"].permissions.append(
            Permission(code=f"{resource}:{action}", resource=resource, action=action, name=f"{resource} {action}", is_active=True)
        )
    db_session.commit()
    return test_data


@pytest.fixture
def migrated(db_session, full_access):
    bind = db_session.get_bind()
    upgrade_database(bind)
    try:
        yield full_access
    finally:
        db_session.rollback()
        cleanup(bind)


def test_permissions_and_missing_certification_migration(client, db_session, admin_token, employee_token, full_access):
    assert client.get(SUMMARY).status_code == 401
    assert client.get(ACTIVITY, headers=auth(employee_token)).status_code == 403
    assert client.get(SUMMARY, headers=auth(employee_token)).status_code == 403
    full_access["inactive_permission_group"].permissions.append(full_access["permissions"]["employees:read"])
    db_session.commit()

    limited = client.get(SUMMARY, headers=auth(employee_token))
    assert limited.status_code == 200, limited.text
    assert limited.headers["Cache-Control"] == "no-store"
    visible = {key for key, value in limited.json().items() if value is not None}
    assert visible == {"as_of", "period_start", "employees"}
    assert limited.json()["employees"] == {"active": 2, "inactive": 1}
    assert client.get(ACTIVITY, headers=auth(employee_token)).status_code == 403
    admin = client.get(SUMMARY, headers=auth(admin_token)).json()
    assert admin["certification_available"] is False and admin["certification"] is None


def test_zero_counts_inventory_and_migration_index(client, db_session, admin_token, migrated):
    bind = db_session.get_bind()
    index = next(row for row in inspect(bind).get_indexes("audit_events") if row["name"] == "ix_audit_events_created_at_id")
    assert index["column_names"] == ["created_at", "id"]
    response = client.get(SUMMARY, headers=auth(admin_token))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["employees"] == {"active": 2, "inactive": 1}
    assert data["departments"] == {"active": 1, "inactive": 0}
    assert data["groups"] == {"active": 2, "inactive": 1}
    assert data["permissions"]["inactive"] == 1
    assert data["pending_requests"] == 0
    assert data["reviews"] == {"pending": 0, "decisions": {"retained": 0, "revoked": 0}}
    assert data["certification_available"] is True
    assert data["certification"]["active_campaigns"] == 0
    assert set(data["activity"].values()) == {0}
    assert client.get(ACTIVITY, headers=auth(admin_token)).json() == {"items": [], "next_before_id": None}


def test_membership_counts_deduplicate_and_ignore_inactive_privileges(client, db_session, admin_token, full_access):
    admin, inactive = full_access["admin"], full_access["inactive_employee"]
    inactive.groups.extend([full_access["admin_group"], full_access["inactive_permission_group"], full_access["inactive_group"]])
    disabled_privilege = Permission(code="certifications:review", name="Disabled certificate reviewer",
                                   resource="certifications", action="review", is_active=False)
    admin.groups.append(Group(name="Dormant privilege", code="DORMANT", is_active=True, permissions=[disabled_privilege]))
    db_session.commit()
    data = client.get(SUMMARY, headers=auth(admin_token)).json()
    assert data["security"] == {"privileged_memberships": 1, "inactive_accounts_with_active_groups": 1}


def test_backlog_transitions_and_window(client, db_session, admin_token, full_access):
    employee, group, admin = (full_access[name] for name in ("employee", "inactive_permission_group", "admin"))
    request = AccessRequest(employee_id=employee.id, group_id=group.id, reason="example", status="pending")
    review = AccessReview(employee_id=employee.id, group_id=group.id, opened_by=admin.id, status="pending")
    db_session.add_all([request, review])
    db_session.commit()
    before = client.get(SUMMARY, headers=auth(admin_token)).json()
    assert before["pending_requests"] == before["reviews"]["pending"] == 1

    request.status = "rejected"
    review.status = "retained"
    review.decided_at = NOW - timedelta(days=8)
    db_session.commit()
    week = client.get(SUMMARY, headers=auth(admin_token), params={"days": 7}).json()
    month = client.get(SUMMARY, headers=auth(admin_token), params={"days": 30}).json()
    assert week["pending_requests"] == month["pending_requests"] == 0
    assert week["reviews"]["pending"] == month["reviews"]["pending"] == 0
    assert week["reviews"]["decisions"]["retained"] == 0
    assert month["reviews"]["decisions"]["retained"] == 1


def test_campaign_snapshot_inclusive_deadline_and_activity_window(client, db_session, admin_token, migrated):
    actor = migrated["admin"]
    employee = migrated["employee"]
    group = migrated["inactive_permission_group"]
    for offset, campaign_status, item_status in [(-1, "active", "pending"), (0, "active", "pending"),
                                                  (-2, "completed", "retained"), (-3, "active", "revoked"),
                                                  (0, "active", "superseded")]:
        campaign = CertificationCampaign(
            owner_id=actor.id, name="Fixture campaign", status=campaign_status,
            starts_on=NOW.date() - timedelta(days=10), due_on=NOW.date() + timedelta(days=offset),
        )
        db_session.add(campaign)
        db_session.flush()
        item = CertificationItem(campaign_id=campaign.id, employee_id=employee.id, group_id=group.id, status=item_status)
        if item_status in ("retained", "revoked"):
            item.reviewer_id = actor.id
            item.justification = "Fixture decision"
            item.decided_at = NOW - timedelta(days=8 if item_status == "retained" else 2)
        db_session.add(item)
    db_session.commit()
    result = client.get(SUMMARY, headers=auth(admin_token), params={"days": 7})
    assert result.status_code == 200, result.text
    assert result.json()["certification"] == {
        "active_campaigns": 4, "overdue_campaigns": 2, "overdue_items": 1, "pending": 2,
        "retained": 0, "revoked": 1, "superseded": 1, "decisions": {"retained": 0, "revoked": 1},
    }
    period = client.get(SUMMARY, headers=auth(admin_token), params={"days": 30}).json()["certification"]
    assert period["decisions"] == {"retained": 1, "revoked": 1}


def test_activity_order_filter_pagination_and_redaction(client, db_session, admin_token, full_access):
    events = []
    for action, offset in [("lifecycle.joiner", -30), ("lifecycle.mover", -8), ("lifecycle.leaver", -1),
                           ("employee.group.removed", -1), ("review.revoked", -1),
                           ("certification.item_revoked", -2), ("entra.sync.failed", -2), ("request.rejected", -2),
                           ("unrecognized.private@example.test", -1), ("lifecycle.joiner", 1)]:
        event = AuditEvent(action=action, created_at=NOW + timedelta(days=offset),
                           actor_id=full_access["admin"].id, target_type="private@example.test",
                           target_id=99, details={"secret": "not exposed"})
        events.append(event)
        db_session.add(event)
    db_session.commit()
    headers = auth(admin_token)
    data = client.get(SUMMARY, headers=headers).json()["activity"]
    assert data == {"joiners": 1, "movers": 1, "leavers": 1, "revocation_events": 3, "failed_entra_syncs": 1}
    week = client.get(SUMMARY, headers=headers, params={"days": 7}).json()["activity"]
    assert week["joiners"] == week["movers"] == 0
    first = client.get(ACTIVITY, headers=headers, params={"category": "access", "limit": 1}).json()
    assert [row["id"] for row in first["items"]] == [events[4].id]
    assert first["next_before_id"] == events[4].id
    second = client.get(ACTIVITY, headers=headers, params={
        "category": "access", "limit": 2, "before_id": first["next_before_id"],
    }).json()
    assert [row["id"] for row in second["items"]] == [events[3].id, events[7].id]
    assert second["next_before_id"] is None
    other = client.get(ACTIVITY, headers=headers, params={"category": "other"})
    assert "private@example.test" not in other.text and "not exposed" not in other.text
    event, = other.json()["items"]
    assert event == {"id": events[8].id, "created_at": "2026-07-09T14:00:00Z", "category": "other", "label": "Audit event"}
    assert client.get(ACTIVITY, headers=headers, params={"before_id": 999999}).json()["items"] == []
    assert client.get(ACTIVITY, headers=headers, params={"category": "unknown"}).status_code == 422
    assert client.get(SUMMARY, headers=headers, params={"days": 365}).status_code == 422


def test_storage_failure_returns_sanitized_error(client, admin_token, full_access, monkeypatch):
    def broken(*args):
        raise SQLAlchemyError("Sensitive internal details")

    monkeypatch.setattr(dashboard_service, "summary", broken)
    response = client.get(SUMMARY, headers=auth(admin_token))
    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard data is temporarily unavailable"}
