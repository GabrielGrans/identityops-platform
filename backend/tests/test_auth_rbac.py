def test_login_with_valid_credentials(client, test_data):
    response = client.post(
        "/auth/login",
        json={
            "email": "admin@test.identityops.com",
            "password": "AdminPassword123!",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_with_invalid_password(client, test_data):
    response = client.post(
        "/auth/login",
        json={
            "email": "admin@test.identityops.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_login_with_nonexistent_email(client):
    response = client.post(
        "/auth/login",
        json={
            "email": "unknown@test.identityops.com",
            "password": "SomePassword123!",
        },
    )

    assert response.status_code == 401


def test_inactive_employee_cannot_login(client, test_data):
    response = client.post(
        "/auth/login",
        json={
            "email": "inactive@test.identityops.com",
            "password": "InactivePassword123!",
        },
    )

    assert response.status_code == 403


def test_authenticated_employee_can_access_profile(
    client,
    admin_token,
):
    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {admin_token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "admin@test.identityops.com"


def test_employees_endpoint_requires_authentication(client):
    response = client.get("/employees")

    assert response.status_code == 401


def test_invalid_token_is_rejected(client):
    response = client.get(
        "/employees",
        headers={
            "Authorization": "Bearer invalid.token.value",
        },
    )

    assert response.status_code == 401


def test_employee_without_permission_is_forbidden(
    client,
    employee_token,
    test_data,
):
    response = client.get(
        "/employees",
        headers={
            "Authorization": f"Bearer {employee_token}",
        },
    )

    assert response.status_code == 403


def test_admin_with_permission_can_read_employees(
    client,
    admin_token,
    test_data,
):
    response = client.get(
        "/employees",
        headers={
            "Authorization": f"Bearer {admin_token}",
        },
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_inactive_group_does_not_grant_permission(
    client,
    employee_token,
    test_data,
):
    response = client.get(
        "/departments",
        headers={
            "Authorization": f"Bearer {employee_token}",
        },
    )

    assert response.status_code == 403


def test_inactive_employee_token_is_rejected(
    client,
    inactive_employee_token,
    test_data,
):
    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {inactive_employee_token}",
        },
    )

    assert response.status_code == 401
