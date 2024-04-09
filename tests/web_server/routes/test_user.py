from fastapi.testclient import TestClient

from ouranos import json


def test_get_users_fail_not_admin(client_operator: TestClient):
    response = client_operator.get("/api/user/")
    assert response.status_code == 403


def test_get_users_success(client_admin: TestClient):
    response = client_admin.get("/api/user/")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 4  # Ouranos, user, operator and administrator


def test_get_user_failure_different_user(client_operator: TestClient):
    response = client_operator.get("/api/user/u/Ouranos")
    assert response.status_code == 403


def test_get_user_success_same_user(client_operator: TestClient):
    username = "Her"
    response = client_operator.get(f"/api/user/u/{username}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["username"] == username


def test_get_user_success_admin(client_admin: TestClient):
    username = "Her"
    response = client_admin.get(f"/api/user/u/{username}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["username"] == username


def test_update_user_failure_different_user(client_user: TestClient):
    payload = {"firstname": "Ouranos"}

    response = client_user.put(
        "/api/user/u/Ouranos",
        json=payload,
    )
    assert response.status_code == 403


def test_update_user_success_same_user(client_user: TestClient):
    payload = {"firstname": "Frank"}

    response = client_user.put(
        "/api/user/u/Who",
        json=payload,
    )
    assert response.status_code == 202


def test_update_user_success_admin(client_admin: TestClient):
    payload = {"firstname": "Frank"}

    response = client_admin.put(
        "/api/user/u/Who",
        json=payload,
    )
    assert response.status_code == 202


def test_update_user_failure_other_admin(client_admin: TestClient):
    payload = {"firstname": "Ouranos"}

    response = client_admin.put(
        "/api/user/u/Ouranos",
        json=payload,
    )
    assert response.status_code == 403
