from backend.app.services import employee_service


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def employee_update_payload(employee, **overrides):
    payload = {
        "employee_number": employee.employee_number,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "email": employee.email,
        "job_title": employee.job_title,
        "department_id": employee.department_id,
        "manager_id": employee.manager_id,
    }

    payload.update(overrides)

    return payload


def test_update_endpoint_cannot_deactivate_employee(
    client,
    admin_token,
    test_data,
):
    employee = test_data["employee"]

    response = client.put(
        f"/employees/{employee.id}",
        headers=auth(admin_token),
        json=employee_update_payload(
            employee,
            status="inactive",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_update_endpoint_cannot_reactivate_inactive_employee(
    client,
    admin_token,
    test_data,
):
    employee = test_data["inactive_employee"]

    response = client.put(
        f"/employees/{employee.id}",
        headers=auth(admin_token),
        json=employee_update_payload(
            employee,
            status="active",
        ),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "inactive"


def test_employee_service_ignores_status_update(
    db_session,
    test_data,
):
    employee = test_data["employee"]

    result = employee_service.update_employee(
        db_session,
        employee,
        employee_update_payload(
            employee,
            status="inactive",
        ),
    )

    assert result.status == "active"


def test_update_employee_cannot_create_manager_hierarchy_cycle(
    client,
    admin_token,
    test_data,
):
    department_id = test_data["department"].id
    headers = auth(admin_token)

    first_response = client.post(
        "/employees",
        headers=headers,
        json={
            "employee_number": "CYCLE001",
            "first_name": "First",
            "last_name": "Employee",
            "email": "cycle.first@test.identityops.com",
            "job_title": "IT Manager",
            "department_id": department_id,
        },
    )

    assert first_response.status_code == 201
    first_id = first_response.json()["id"]

    second_response = client.post(
        "/employees",
        headers=headers,
        json={
            "employee_number": "CYCLE002",
            "first_name": "Second",
            "last_name": "Employee",
            "email": "cycle.second@test.identityops.com",
            "job_title": "IT Analyst",
            "department_id": department_id,
            "manager_id": first_id,
        },
    )

    assert second_response.status_code == 201
    second_id = second_response.json()["id"]

    third_response = client.post(
        "/employees",
        headers=headers,
        json={
            "employee_number": "CYCLE003",
            "first_name": "Third",
            "last_name": "Employee",
            "email": "cycle.third@test.identityops.com",
            "job_title": "IT Analyst",
            "department_id": department_id,
            "manager_id": second_id,
        },
    )

    assert third_response.status_code == 201
    third_id = third_response.json()["id"]

    first_employee = first_response.json()

    update_response = client.put(
        f"/employees/{first_id}",
        headers=headers,
        json={
            "employee_number": first_employee["employee_number"],
            "first_name": first_employee["first_name"],
            "last_name": first_employee["last_name"],
            "email": first_employee["email"],
            "job_title": first_employee["job_title"],
            "department_id": department_id,
            "manager_id": third_id,
        },
    )

    assert update_response.status_code == 400
    assert "hierarchy cycle" in update_response.text
