import asyncio
import importlib

from backend.app.core import database as database_module
from backend.app.services import group_service


main_module = importlib.import_module("backend.app.main")


def test_get_db_closes_session_after_normal_execution(monkeypatch):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    fake_session = FakeSession()

    monkeypatch.setattr(
        database_module,
        "SessionLocal",
        lambda: fake_session,
    )

    generator = database_module.get_db()

    yielded_session = next(generator)

    assert yielded_session is fake_session
    assert fake_session.closed is False

    generator.close()

    assert fake_session.closed is True


def test_get_db_closes_session_after_exception(monkeypatch):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    fake_session = FakeSession()

    monkeypatch.setattr(
        database_module,
        "SessionLocal",
        lambda: fake_session,
    )

    generator = database_module.get_db()

    assert next(generator) is fake_session

    try:
        generator.throw(RuntimeError("Simulated database error"))
    except RuntimeError as error:
        assert str(error) == "Simulated database error"

    assert fake_session.closed is True


def test_lifespan_creates_tables_and_disposes_engine(monkeypatch):
    events = []

    class FakeMetadata:
        def create_all(self, bind):
            events.append(("create_all", bind))

    class FakeBase:
        metadata = FakeMetadata()

    class FakeEngine:
        def dispose(self):
            events.append(("dispose",))

    fake_engine = FakeEngine()

    monkeypatch.setattr(main_module, "Base", FakeBase)
    monkeypatch.setattr(main_module, "engine", fake_engine)

    async def run_lifespan():
        async with main_module.lifespan(main_module.app):
            events.append(("started",))

    asyncio.run(run_lifespan())

    assert events == [
        ("create_all", fake_engine),
        ("started",),
        ("dispose",),
    ]


def test_assign_permission_does_not_duplicate_existing_assignment(
    db_session,
    test_data,
):
    group = test_data["admin_group"]
    permission = test_data["permissions"]["employees:read"]

    original_count = len(group.permissions)

    result = group_service.assign_permission(
        db_session,
        group.id,
        permission.id,
    )

    assert result.id == group.id
    assert len(group.permissions) == original_count
    assert permission in group.permissions


def test_assign_employee_does_not_duplicate_existing_membership(
    db_session,
    test_data,
):
    employee = test_data["admin"]
    group = test_data["admin_group"]

    original_count = len(employee.groups)

    result = group_service.assign_employee(
        db_session,
        employee.id,
        group.id,
    )

    assert result.id == employee.id
    assert len(employee.groups) == original_count
    assert group in employee.groups
