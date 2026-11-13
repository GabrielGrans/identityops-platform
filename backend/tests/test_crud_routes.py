def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# EMPLOYEES
# ============================================================

def test_create_employee(client, admin_token, test_data):
    response = client.post(
        "/employees",
        headers=auth(admin_token),
        json={
            "employee_number": "NEW001",
            "first_name": "Maria",
            "last_name": "Silva",
            "email": "maria.silva@test.identityops.com",
            "job_title": "Security Analyst",
            "department_id": test_data["department"].id,
        },
    )

    assert response.status_code == 201
    assert response.json()["employee_number"] == "NEW001"


def test_create_employee_with_duplicate_email(
    client,
    admin_token,
    test_data,
):
    response = client.post(
        "/employees",
        headers=auth(admin_token),
        json={
            "employee_number": "NEW004",
            "first_name": "Another",
            "last_name": "User",
            "email": "employee@test.identityops.com",
            "job_title": "Analyst",
        },
    )

    assert response.status_code == 400


def test_update_employee(client, admin_token, test_data):
    employee_id = test_data["employee"].id

    response = client.put(
        f"/employees/{employee_id}",
        headers=auth(admin_token),
        json={
            "employee_number": "TEST002",
            "first_name": "Regular",
            "last_name": "User",
            "email": "employee@test.identityops.com",
            "job_title": "Senior IT Support Analyst",
            "department_id": test_data["department"].id,
            "manager_id": None,
            "status": "active",
        },
    )

    assert response.status_code == 200
    assert response.json()["job_title"] == "Senior IT Support Analyst"


def test_deactivate_employee(client, admin_token, test_data):
    employee_id = test_data["employee"].id

    response = client.delete(
        f"/employees/{employee_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "inactive"


def test_get_nonexistent_employee(client, admin_token):
    response = client.get(
        "/employees/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


# ============================================================
# DEPARTMENTS
# ============================================================

def test_create_department(client, admin_token):
    response = client.post(
        "/departments",
        headers=auth(admin_token),
        json={
            "name": "Human Resources",
            "code": "HR",
            "description": "Human Resources department",
        },
    )

    assert response.status_code == 201
    assert response.json()["code"] == "HR"


def test_create_department_with_duplicate_code(
    client,
    admin_token,
    test_data,
):
    response = client.post(
        "/departments",
        headers=auth(admin_token),
        json={
            "name": "Another IT Department",
            "code": "IT",
            "description": "Duplicate code test",
        },
    )

    assert response.status_code == 409


def test_update_department(client, admin_token, test_data):
    department_id = test_data["department"].id

    response = client.put(
        f"/departments/{department_id}",
        headers=auth(admin_token),
        json={
            "name": "Technology Department",
            "code": "TECH",
            "description": "Updated department",
            "is_active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Technology Department"


def test_deactivate_department(client, admin_token, test_data):
    department_id = test_data["department"].id

    response = client.delete(
        f"/departments/{department_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_get_nonexistent_department(client, admin_token):
    response = client.get(
        "/departments/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


# ============================================================
# GROUPS
# ============================================================

def test_create_group(client, admin_token):
    response = client.post(
        "/groups",
        headers=auth(admin_token),
        json={
            "name": "Security Analysts",
            "code": "SECURITY_ANALYSTS",
            "description": "Security team",
        },
    )

    assert response.status_code == 201
    assert response.json()["code"] == "SECURITY_ANALYSTS"


def test_create_group_with_duplicate_code(
    client,
    admin_token,
    test_data,
):
    response = client.post(
        "/groups",
        headers=auth(admin_token),
        json={
            "name": "Another Admin Group",
            "code": "TEST_ADMINS",
            "description": "Duplicate group test",
        },
    )

    assert response.status_code == 409


def test_update_group(client, admin_token, test_data):
    group_id = test_data["admin_group"].id

    response = client.put(
        f"/groups/{group_id}",
        headers=auth(admin_token),
        json={
            "name": "Updated Test Administrators",
            "code": "TEST_ADMINS_UPDATED",
            "description": "Updated administrator group",
            "is_active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Test Administrators"


def test_deactivate_group(client, admin_token, test_data):
    group_id = test_data["admin_group"].id

    response = client.delete(
        f"/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_assign_permission_to_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id
    permission_id = test_data["extra_permission"].id

    response = client.post(
        f"/groups/{group_id}/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200


def test_remove_permission_from_group(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id
    permission_id = test_data["permissions"]["employees:read"].id

    response = client.delete(
        f"/groups/{group_id}/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200


def test_assign_inactive_permission_to_group_is_rejected(
    client,
    admin_token,
    test_data,
):
    group_id = test_data["admin_group"].id
    permission_id = test_data["inactive_permission"].id

    response = client.post(
        f"/groups/{group_id}/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 400


# ============================================================
# PERMISSIONS
# ============================================================

def test_create_permission(client, admin_token):
    response = client.post(
        "/permissions",
        headers=auth(admin_token),
        json={
            "name": "Manage Reports",
            "code": "reports:create",
            "resource": "reports",
            "action": "create",
            "description": "Allows creating reports",
        },
    )

    assert response.status_code == 201
    assert response.json()["code"] == "reports:create"


def test_create_permission_with_duplicate_code(
    client,
    admin_token,
    test_data,
):
    response = client.post(
        "/permissions",
        headers=auth(admin_token),
        json={
            "name": "Another Read Employees",
            "code": "employees:read",
            "resource": "another_resource",
            "action": "read",
            "description": "Duplicate permission test",
        },
    )

    assert response.status_code == 409


def test_update_permission(client, admin_token, test_data):
    permission_id = test_data["extra_permission"].id

    response = client.put(
        f"/permissions/{permission_id}",
        headers=auth(admin_token),
        json={
            "name": "View Company Reports",
            "code": "reports:read",
            "resource": "reports",
            "action": "read",
            "description": "Updated report permission",
            "is_active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "View Company Reports"


def test_deactivate_permission(client, admin_token, test_data):
    permission_id = test_data["extra_permission"].id

    response = client.delete(
        f"/permissions/{permission_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_get_nonexistent_permission(client, admin_token):
    response = client.get(
        "/permissions/99999",
        headers=auth(admin_token),
    )

    assert response.status_code == 404


# ============================================================
# EMPLOYEE GROUP MEMBERSHIPS
# ============================================================

def test_assign_employee_to_group(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["employee"].id
    group_id = test_data["admin_group"].id

    response = client.post(
        f"/employees/{employee_id}/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == group_id


def test_remove_employee_from_group(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["employee"].id
    group_id = test_data["inactive_group"].id

    response = client.delete(
        f"/employees/{employee_id}/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 200
    assert response.json()["employee_id"] == employee_id


def test_cannot_assign_inactive_employee_to_group(
    client,
    admin_token,
    test_data,
):
    employee_id = test_data["inactive_employee"].id
    group_id = test_data["admin_group"].id

    response = client.post(
        f"/employees/{employee_id}/groups/{group_id}",
        headers=auth(admin_token),
    )

    assert response.status_code == 400


# ============================================================
# RBAC: ADMINISTRATIVE OPERATIONS
# ============================================================

def test_regular_employee_cannot_create_employee(
    client,
    employee_token,
):
    response = client.post(
        "/employees",
        headers=auth(employee_token),
        json={
            "employee_number": "BLOCK001",
            "first_name": "Blocked",
            "last_name": "User",
            "email": "blocked@test.identityops.com",
            "job_title": "Unauthorized User",
        },
    )

    assert response.status_code == 403


def test_regular_employee_cannot_create_group(
    client,
    employee_token,
):
    response = client.post(
        "/groups",
        headers=auth(employee_token),
        json={
            "name": "Unauthorized Group",
            "code": "UNAUTHORIZED_GROUP",
        },
    )

    assert response.status_code == 403


def test_regular_employee_cannot_create_permission(
    client,
    employee_token,
):
    response = client.post(
        "/permissions",
        headers=auth(employee_token),
        json={
            "name": "Unauthorized Permission",
            "code": "unauthorized:create",
            "resource": "unauthorized",
            "action": "create",
        },
    )

    assert response.status_code == 403


def test_regular_employee_cannot_assign_group(
    client,
    employee_token,
    test_data,
):
    employee_id = test_data["employee"].id
    group_id = test_data["admin_group"].id

    response = client.post(
        f"/employees/{employee_id}/groups/{group_id}",
        headers=auth(employee_token),
    )

    assert response.status_code == 403
