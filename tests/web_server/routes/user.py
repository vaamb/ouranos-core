from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import User


def test_get_users_fail_not_admin(client_operator: TestClient):
    response = client_operator.get("/api/user")
    assert response.status_code == 403


def test_get_users_success(client_admin: TestClient):
    response = client_admin.get(
        "/api/user",
        params={
            "active": True,
        }
    )
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


@pytest.mark.asyncio
async def test_update_user_success_same_user(
        client_user: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    username = "Who"
    firstname = "Alice"
    payload = {"firstname": firstname}

    response = client_user.put(
        f"/api/user/u/{username}",
        json=payload,
    )
    assert response.status_code == 202

    async with db.scoped_session() as session:
        user = await User.get_by(session, username=username)
        assert user.firstname == firstname


@pytest.mark.asyncio
async def test_update_user_success_admin(
        client_admin: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    username = "Who"
    firstname = "Bob"
    payload = {"firstname": firstname}

    response = client_admin.put(
        f"/api/user/u/{username}",
        json=payload,
    )
    assert response.status_code == 202

    async with db.scoped_session() as session:
        user = await User.get_by(session, username=username)
        assert user.firstname == firstname


def test_update_user_failure_other_admin(client_admin: TestClient):
    payload = {"firstname": "Ouranos"}

    response = client_admin.put(
        "/api/user/u/Ouranos",
        json=payload,
    )
    assert response.status_code == 403
