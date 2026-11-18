from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.app.main import app
import backend.app.main as main_module


def admin_headers(admin_token):
    return {
        "Authorization": f"Bearer {admin_token}"
    }


def employee_payload(
    employee_number="EMP-TEST-9001",
    email="new.employee9001@example.com",
    department_id=None,
    manager_id=None,
):
    return {
        "employee_number": employee_number,
        "first_name": "Test",
        "last_name": "Employee",
        "email": email,
        "job_title": "Software Engineer",
        "department_id": department_id,
        "manager_id": manager_id,
    }


# ============================================================
# EMPLOYEE SERVICE - FILTERS
# ============================================================

def test_list_employees_filtered_by_department(
    client,
    test_data,
    admin_token,
):
    response = client.get(
        f"/employees?department_id={test_data['department'].id}",
        headers=admin_headers(admin_token),
    )

    assert response.status_code == 200
    assert all(
        employee["department_id"] == test_data["department"].id
        for employee in response.json()
    )


def test_list_employees_filtered_by_status(
    client,
    test_data,
    admin_token,
):
    response = client.get(
        "/employees?status=inactive",
        headers=admin_headers(admin_token),
    )

    assert response.status_code == 200
    assert all(
        employee["status"] == "inactive"
        for employee in response.json()
    )


# ============================================================
# EMPLOYEE SERVICE - RELATIONSHIP VALIDATION
# ============================================================

def test_create_employee_with_nonexistent_department(
    client,
    test_data,
    admin_token,
):
    payload = employee_payload(
        department_id=999999,
    )

    response = client.post(
        "/employees",
        json=payload,
        headers=admin_headers(admin_token),
    )

    assert response.status_code == 400
    assert "Department not found or inactive" in response.text


def test_create_employee_with_nonexistent_manager(
    client,
    test_data,
    admin_token,
):
    payload = employee_payload(
        employee_number="EMP-TEST-9002",
        email="new.employee9002@example.com",
        manager_id=999999,
    )

    response = client.post(
        "/employees",
        json=payload,
        headers=admin_headers(admin_token),
    )

    assert response.status_code == 400
    assert "Manager not found or inactive" in response.text


def test_create_employee_with_inactive_manager(
    client,
    test_data,
    admin_token,
):
    payload = employee_payload(
        employee_number="EMP-TEST-9003",
        email="new.employee9003@example.com",
        manager_id=test_data["inactive_employee"].id,
    )

    response = client.post(
        "/employees",
        json=payload,
        headers=admin_headers(admin_token),
    )

    assert response.status_code == 400
    assert "Manager not found or inactive" in response.text


def test_update_employee_cannot_be_own_manager(
    client,
    test_data,
    admin_token,
):
    employee = test_data["employee"]

    payload = {
        "employee_number": employee.employee_number,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "email": employee.email,
        "job_title": employee.job_title,
        "department_id": employee.department_id,
        "manager_id": employee.id,
        "status": employee.status,
    }

    response = client.put(
        f"/employees/{employee.id}",
        json=payload,
        headers=admin_headers(admin_token),
    )

    assert response.status_code == 400
    assert "cannot be their own manager" in response.text


def test_create_employee_with_inactive_department(
    client,
    test_data,
    admin_token,
):
    headers = admin_headers(admin_token)

    department_response = client.post(
        "/departments",
        json={
            "name": "Inactive Test Department",
            "code": "INACTIVE_TEST",
            "description": "Department used in automated tests",
        },
        headers=headers,
    )

    assert department_response.status_code == 201

    department_id = department_response.json()["id"]

    deactivate_response = client.delete(
        f"/departments/{department_id}",
        headers=headers,
    )

    assert deactivate_response.status_code == 200

    payload = employee_payload(
        employee_number="EMP-TEST-9004",
        email="new.employee9004@example.com",
        department_id=department_id,
    )

    response = client.post(
        "/employees",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 400
    assert "Department not found or inactive" in response.text


# ============================================================
# EMPLOYEE SERVICE - UNIQUE FIELD VALIDATION
# ============================================================

def test_create_employee_with_duplicate_employee_number(
    client,
    test_data,
    admin_token,
):
    payload = employee_payload(
        employee_number=test_data["admin"].employee_number,
        email="unique.employee9005@example.com",
    )

    response = client.post(
        "/employees",
        json=payload,
        headers=admin_headers(admin_token),
    )

    assert response.status_code == 400
    assert "Employee number already exists" in response.text


# ============================================================
# MAIN API - GENERAL ENDPOINTS
# ============================================================

def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "application": "IdentityOps",
        "message": "IdentityOps API is running",
        "version": "0.9.0",
    }


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "IdentityOps",
    }


# ============================================================
# MAIN API - DATABASE HEALTH
# ============================================================

def test_database_health_connected(client, monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement):
            return SimpleNamespace(scalar=lambda: 1)

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(
        main_module,
        "engine",
        FakeEngine(),
    )

    response = client.get("/health/database")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "database": "connected",
    }


def test_database_health_disconnected(client, monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement):
            raise SQLAlchemyError("Database connection failed")

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(
        main_module,
        "engine",
        FakeEngine(),
    )

    response = client.get("/health/database")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unhealthy",
        "database": "disconnected",
    }


# ============================================================
# MAIN API - CORS
# ============================================================

def test_cors_allows_frontend_origin(client):
    response = client.options(
        "/employees",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://localhost:5173"
    )
