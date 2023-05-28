from fastapi.testclient import TestClient
from httpx import BasicAuth
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.config.consts import TOKEN_SUBS
from ouranos.core.database.models.app import User
from ouranos.core.validate.models.auth import anonymous_user
from ouranos.core.utils import Tokenizer

from ...data.users import admin


registration_payload = {
    "username": "NewUser",
    "password": "Password1!",
    "email": "new_user@fakemail.com",
}


def test_login_no_credential(client: TestClient):
    response = client.get("/api/auth/login")
    assert response.status_code == 401


def test_login_wrong_credential(client: TestClient):
    response = client.get(
        "/api/auth/login",
        auth=BasicAuth("wrong_username", "wrong_password")
    )
    assert response.status_code == 401


def test_login_success(client: TestClient):
    response = client.get("/api/auth/login")
    assert response.status_code == 401
    response = client.get(
        "/api/auth/login",
        auth=BasicAuth(admin.username, admin.password)
    )
    assert response.status_code == 200
    assert response.cookies
    data = json.loads(response.text)
    user = data["user"]
    assert user["username"] == admin.username
    assert user["permissions"] == 15


def test_logout_anonymous(client: TestClient):
    response = client.get("/api/auth/logout")
    assert response.status_code == 200
    assert "not logged in" in response.text


def test_logout_success(client_admin: TestClient):
    response = client_admin.get("/api/auth/logout")
    assert response.status_code == 200
    assert "Logged out" in response.text


def test_current_user_anonymous(client: TestClient):
    response = client.get("/api/auth/current_user")
    assert response.status_code == 200
    data = json.loads(response.text)
    assert data["id"] == anonymous_user.id
    assert data["permissions"] == 0


def test_current_user_admin(client_admin: TestClient):
    response = client_admin.get("/api/auth/current_user")
    assert response.status_code == 200
    data = json.loads(response.text)
    assert data["username"] == admin.username
    assert data["permissions"] == 15


def test_register_no_token(client: TestClient):
    response = client.post("/api/auth/register")
    assert response.status_code == 422
    assert "invitation_token" in response.text


def test_register_no_payload(client: TestClient):
    response = client.post(
        "/api/auth/register",
        params={"invitation_token": "def_not_a_token"},
    )
    assert response.status_code == 422
    assert "body" in response.text


def test_register_invalid_token(client: TestClient):
    response = client.post(
        "/api/auth/register",
        params={"invitation_token": "def_not_a_token"},
        json=registration_payload,
    )
    assert response.status_code == 422
    assert "Invalid token" in response.text


def test_register_logged(client_user: TestClient):
    response = client_user.post(
        "/api/auth/register",
        params={"invitation_token": "def_not_a_token"},
        json=registration_payload,
    )
    assert response.status_code == 406
    assert "Logged in user cannot register" in response.text


@pytest.mark.asyncio
async def test_register_success(db: AsyncSQLAlchemyWrapper, client: TestClient):
    async with db.scoped_session() as session:
        invitation_token = await User.create_invitation_token(session)
    response = client.post(
        "/api/auth/register",
        params={"invitation_token": invitation_token},
        json=registration_payload,
    )
    assert response.status_code == 200
    data = json.loads(response.text)
    assert data["username"] == registration_payload["username"]


def test_registration_token_failure(client: TestClient):
    response = client.get("/api/auth/registration_token")
    assert response.status_code == 403


def test_registration_token_success(client_admin: TestClient):
    response = client_admin.get("/api/auth/registration_token")
    assert response.status_code == 200
    data = json.loads(response.text)
    payload = Tokenizer.loads(data)
    assert payload["sub"] == TOKEN_SUBS.REGISTRATION.value
