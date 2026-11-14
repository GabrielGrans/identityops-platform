import os

os.environ.setdefault(
    "SECRET_KEY",
    "identityops-test-secret-key-not-for-production",
)

import pytest

from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import get_db
from backend.app.core.security import (
    create_access_token,
    hash_password,
)
from backend.app.main import app
from backend.app.models import (
    Base,
    Department,
    Employee,
    Group,
    Permission,
)


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture
def database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session(database):
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(database):
    def override_get_db():
        db = TestingSessionLocal()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    test_client = TestClient(app)

    yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_data(db_session):
    department = Department(
        name="Information Technology",
        code="IT",
        description="IT test department",
        is_active=True,
    )

    admin = Employee(
        employee_number="TEST001",
        first_name="Admin",
        last_name="User",
        email="admin@test.identityops.com",
        password_hash=hash_password("AdminPassword123!"),
        job_title="IT Administrator",
        status="active",
        department=department,
    )

    employee = Employee(
        employee_number="TEST002",
        first_name="Regular",
        last_name="User",
        email="employee@test.identityops.com",
        password_hash=hash_password("EmployeePassword123!"),
        job_title="IT Support Analyst",
        status="active",
        department=department,
    )

    inactive_employee = Employee(
        employee_number="TEST003",
        first_name="Inactive",
        last_name="User",
        email="inactive@test.identityops.com",
        password_hash=hash_password("InactivePassword123!"),
        job_title="Former Employee",
        status="inactive",
        department=department,
    )

    permission_definitions = [
        ("Read Employees", "employees:read", "employees", "read"),
        ("Create Employees", "employees:create", "employees", "create"),
        ("Update Employees", "employees:update", "employees", "update"),
        (
            "Deactivate Employees",
            "employees:deactivate",
            "employees",
            "deactivate",
        ),
        ("Read Departments", "departments:read", "departments", "read"),
        ("Manage Departments", "departments:manage", "departments", "manage"),
        ("Read Groups", "groups:read", "groups", "read"),
        ("Manage Groups", "groups:manage", "groups", "manage"),
        ("Manage Access Assignments", "access:manage", "access", "manage"),
        ("Read Permissions", "permissions:read", "permissions", "read"),
        ("Manage Permissions", "permissions:manage", "permissions", "manage"),
    ]

    permissions = {
        code: Permission(
            name=name,
            code=code,
            resource=resource,
            action=action,
            is_active=True,
        )
        for name, code, resource, action in permission_definitions
    }

    inactive_permission = Permission(
        name="Inactive Test Permission",
        code="reports:manage",
        resource="reports",
        action="manage",
        is_active=False,
    )

    extra_permission = Permission(
        name="View Reports",
        code="reports:read",
        resource="reports",
        action="read",
        is_active=True,
    )

    admin_group = Group(
        name="Test Administrators",
        code="TEST_ADMINS",
        description="Test administrator group",
        is_active=True,
        permissions=list(permissions.values()),
    )

    inactive_group = Group(
        name="Inactive Group",
        code="TEST_INACTIVE",
        description="Inactive test group",
        is_active=False,
        permissions=[permissions["departments:read"]],
    )

    inactive_permission_group = Group(
        name="Inactive Permission Group",
        code="TEST_INACTIVE_PERMISSION",
        description="Group with inactive permission",
        is_active=True,
        permissions=[inactive_permission],
    )

    admin.groups.append(admin_group)
    employee.groups.extend(
        [
            inactive_group,
            inactive_permission_group,
        ]
    )

    db_session.add_all(
        [
            department,
            admin,
            employee,
            inactive_employee,
            admin_group,
            inactive_group,
            inactive_permission_group,
            *permissions.values(),
            inactive_permission,
            extra_permission,
        ]
    )

    db_session.commit()

    return {
        "department": department,
        "admin": admin,
        "employee": employee,
        "inactive_employee": inactive_employee,
        "admin_group": admin_group,
        "inactive_group": inactive_group,
        "inactive_permission_group": inactive_permission_group,
        "permissions": permissions,
        "inactive_permission": inactive_permission,
        "extra_permission": extra_permission,
    }


@pytest.fixture
def admin_token(test_data):
    return create_access_token(test_data["admin"].id)


@pytest.fixture
def employee_token(test_data):
    return create_access_token(test_data["employee"].id)


@pytest.fixture
def inactive_employee_token(test_data):
    return create_access_token(
        test_data["inactive_employee"].id
    )
