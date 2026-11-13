def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# GROUPS
# ============================================================

def test_list_groups(client, admin_token):
    response = client.get(
        "/groups",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_existing_group(client, admin_token, test_data):
    group_id = test_data["admin_group"].id

    response = client.get(
        f"/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == group_id


def test_get_nonexistent_group(client, admin_token):
    response = client.get(
        "/groups/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_update_nonexistent_group(client, admin_token):
    response = client.put(
        "/groups/99999",
        headers=auth(admin_token),
        json={
            "name": "Unknown Group",
            "code": "UNKNOWN_GROUP",
            "description": "Test",
            "is_active": True,
        },
    )

    assert response.status_code == 404


def test_update_group_with_duplicate_code(
    client,
    admin_token,
    test_data,
):
    admin_group = test_data["admin_group"]
    inactive_group = test_data["inactive_group"]

    response = client.put(
        f"/groups/{admin_group.id}",
        headers=auth(admin_token),
        json={
            "name": "Updated Administrators",
            "code": inactive_group.code,
            "description": "Duplicate code test",
            "is_active": True,
        },
    )

    assert response.status_code == 409


def test_deactivate_nonexistent_group(client, admin_token):
    response = client.delete(
        "/groups/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_assign_permission_to_nonexistent_group(
    client,
    admin_token,
    test_data,
):
    permission_id = test_data["permissions"]["employees:read"].id

    response = client.post(
        f"/groups/99999/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_assign_nonexistent_permission_to_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id

    response = client.post(
        f"/groups/{group_id}/permissions/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_remove_permission_from_nonexistent_group(
    client,
    admin_token,
    test_data,
):
    permission_id = test_data["permissions"]["employees:read"].id

    response = client.delete(
        f"/groups/99999/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_remove_nonexistent_permission_from_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id

    response = client.delete(
        f"/groups/{group_id}/permissions/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_remove_permission_not_assigned_to_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id
    permission_id = test_data["extra_permission"].id

    response = client.delete(
        f"/groups/{group_id}/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 400


def test_assign_permission_already_assigned_to_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id
    permission_id = test_data["permissions"]["employees:read"].id

    response = client.post(
        f"/groups/{group_id}/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200


# ============================================================
# EMPLOYEE GROUP MEMBERSHIPS
# ============================================================

def test_assign_nonexistent_employee_to_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id

    response = client.post(
        f"/employees/99999/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_assign_employee_to_nonexistent_group(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["employee"].id

    response = client.post(
        f"/employees/{employee_id}/groups/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_remove_nonexistent_employee_from_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id

    response = client.delete(
        f"/employees/99999/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_remove_employee_from_nonexistent_group(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["employee"].id

    response = client.delete(
        f"/employees/{employee_id}/groups/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


def test_remove_employee_from_group_they_do_not_belong_to(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["employee"].id
    group_id = test_data["admin_group"].id

    response = client.delete(
        f"/employees/{employee_id}/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 400


def test_assign_employee_to_group_twice(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["employee"].id
    group_id = test_data["admin_group"].id

    first_response = client.post(
        f"/employees/{employee_id}/groups/{group_id}",
        headers=auth(admin_token),
    )

    second_response = client.post(
        f"/employees/{employee_id}/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200


# ============================================================
# EMPLOYEES
# ============================================================

def test_list_employees(client, admin_token):
    response = client.get(
        "/employees",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_existing_employee(client, admin_token, test_data):
    employee_id = test_data["employee"].id

    response = client.get(
        f"/employees/{employee_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == employee_id


def test_update_nonexistent_employee(client, admin_token):
    response = client.put(
        "/employees/99999",
        headers=auth(admin_token),
        json={
            "employee_number": "UNKNOWN001",
            "first_name": "Unknown",
            "last_name": "Employee",
            "email": "unknown@test.identityops.com",
            "job_title": "Analyst",
            "department_id": None,
            "manager_id": None,
            "status": "active",
        },
    )

    assert response.status_code == 404


def test_update_employee_with_duplicate_email(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["employee"].id
    admin_email = test_data["admin"].email

    response = client.put(
        f"/employees/{employee_id}",
        headers=auth(admin_token),
        json={
            "employee_number": "TEST002",
            "first_name": "Regular",
            "last_name": "User",
            "email": admin_email,
            "job_title": "IT Analyst",
            "department_id": test_data["department"].id,
            "manager_id": None,
            "status": "active",
        },
    )

    assert response.status_code == 400


def test_deactivate_nonexistent_employee(client, admin_token):
    response = client.delete(
        "/employees/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


# ============================================================
# DEPARTMENTS
# ============================================================

def test_list_departments(client, admin_token):
    response = client.get(
        "/departments",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_existing_department(client, admin_token, test_data):
    department_id = test_data["department"].id

    response = client.get(
        f"/departments/{department_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == department_id


def test_update_nonexistent_department(client, admin_token):
    response = client.put(
        "/departments/99999",
        headers=auth(admin_token),
        json={
            "name": "Unknown Department",
            "code": "UNKNOWN",
            "description": "Test",
            "is_active": True,
        },
    )

    assert response.status_code == 404


def test_update_department_with_duplicate_code(
    client,
    admin_token,
    test_data,
):
    create_response = client.post(
        "/departments",
        headers=auth(admin_token),
        json={
            "name": "Finance",
            "code": "FIN",
            "description": "Finance department",
        },
    )

    assert create_response.status_code == 201

    department_id = test_data["department"].id

    response = client.put(
        f"/departments/{department_id}",
        headers=auth(admin_token),
        json={
            "name": "Updated IT",
            "code": "FIN",
            "description": "Duplicate code test",
            "is_active": True,
        },
    )

    assert response.status_code == 409


def test_deactivate_nonexistent_department(client, admin_token):
    response = client.delete(
        "/departments/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


# ============================================================
# PERMISSIONS
# ============================================================

def test_list_permissions(client, admin_token):
    response = client.get(
        "/permissions",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_existing_permission(client, admin_token, test_data):
    permission_id = test_data["permissions"]["employees:read"].id

    response = client.get(
        f"/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == permission_id


def test_update_nonexistent_permission(client, admin_token):
    response = client.put(
        "/permissions/99999",
        headers=auth(admin_token),
        json={
            "name": "Unknown Permission",
            "code": "unknown:read",
            "resource": "unknown",
            "action": "read",
            "description": "Test",
            "is_active": True,
        },
    )

    assert response.status_code == 404


def test_update_permission_with_duplicate_code(
    client,
    admin_token,
    test_data,
):
    permission_id = test_data["extra_permission"].id

    response = client.put(
        f"/permissions/{permission_id}",
        headers=auth(admin_token),
        json={
            "name": "Duplicate Permission",
            "code": "employees:read",
            "resource": "employees",
            "action": "read",
            "description": "Duplicate code test",
            "is_active": True,
        },
    )

    assert response.status_code == 409


def test_deactivate_nonexistent_permission(client, admin_token):
    response = client.delete(
        "/permissions/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404
