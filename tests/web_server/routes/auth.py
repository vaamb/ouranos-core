from datetime import datetime

from fastapi.testclient import TestClient
from httpx import BasicAuth
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.config.consts import TOKEN_SUBS
from ouranos.core.database.models.app import anonymous_user, User
from ouranos.core.utils import Tokenizer

from tests.data.auth import admin, operator
from tests.web_server.class_fixtures import UsersAware


registration_payload = {
    "username": "NewUser",
    "password": "Password1!",
    "email": "new_user@fakemail.com",
}


class TestLogin(UsersAware):
    def test_login_no_credential(self, client: TestClient):
        response = client.get("/api/auth/login")
        assert response.status_code == 401

    def test_login_wrong_credential(self, client: TestClient):
        response = client.get(
            "/api/auth/login",
            auth=BasicAuth("wrong_username", "wrong_password")
        )
        assert response.status_code == 401

    def test_login_success(self, client: TestClient):
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

    def test_logout_anonymous(self, client: TestClient):
        response = client.get("/api/auth/logout")
        assert response.status_code == 200
        assert "not logged in" in response.text

    def test_logout_success(self, client_admin: TestClient):
        response = client_admin.get("/api/auth/logout")
        assert response.status_code == 200
        assert "Logged out" in response.text


class TestCurrentUser(UsersAware):
    def test_current_user_anonymous(self, client: TestClient):
        response = client.get("/api/auth/current_user")
        assert response.status_code == 200
        data = json.loads(response.text)
        assert data["id"] == anonymous_user.id
        assert data["permissions"] == 0

    def test_current_user_admin(self, client_admin: TestClient):
        response = client_admin.get("/api/auth/current_user")
        assert response.status_code == 200
        data = json.loads(response.text)
        assert data["username"] == admin.username
        assert data["permissions"] == 15


@pytest.mark.asyncio
class TestRegister(UsersAware):
    def test_register_no_token(self, client: TestClient):
        response = client.post("/api/auth/register")
        assert response.status_code == 422
        assert "invitation_token" in response.text

    def test_register_no_payload(self, client: TestClient):
        response = client.post(
            "/api/auth/register",
            params={"invitation_token": "def_not_a_token"},
        )
        assert response.status_code == 422
        assert "body" in response.text

    def test_register_invalid_token(self, client: TestClient):
        response = client.post(
            "/api/auth/register",
            params={"invitation_token": "def_not_a_token"},
            json=registration_payload,
        )
        assert response.status_code == 422
        assert "Invalid token" in response.text

    def test_register_logged(self, client_user: TestClient):
        response = client_user.post(
            "/api/auth/register",
            params={"invitation_token": "def_not_a_token"},
            json=registration_payload,
        )
        assert response.status_code == 406
        assert "Logged in user cannot register" in response.text

    async def test_register_success(self, db: AsyncSQLAlchemyWrapper, client: TestClient):
        async with db.scoped_session() as session:
            invitation_token = await User.create_invitation_token(session)
        response = client.post(
            "/api/auth/register",
            params={"invitation_token": invitation_token},
            json=registration_payload,
        )
        assert response.status_code == 201
        data = json.loads(response.text)
        assert data["user"]["username"] == registration_payload["username"]

        # Clean up
        async with db.scoped_session() as session:
            user = await User.get_by(session, username=registration_payload["username"])
            await User.delete(session, user_id=user.id)

    @pytest.mark.asyncio
    async def test_register_success_override(self, db: AsyncSQLAlchemyWrapper, client: TestClient):
        username = "Someone"
        email = "test@test.com"
        async with db.scoped_session() as session:
            invitation_token = await User.create_invitation_token(
                session, user_info={"username": username, "email": email})

        response = client.post(
            "/api/auth/register",
            params={"invitation_token": invitation_token},
            json=registration_payload,
        )
        assert response.status_code == 201

        data = json.loads(response.text)
        assert data["user"]["username"] == username

        # Clean up
        async with db.scoped_session() as session:
            user = await User.get_by(session, username=username)
            await User.delete(session, user_id=user.id)


@pytest.mark.asyncio
class TestUserConfirmation(UsersAware):
    async def test_user_confirmation_token_expired(self, db: AsyncSQLAlchemyWrapper, client: TestClient):
        async with db.scoped_session() as session:
            user = await User.get_by(session, username=operator.username)

        token = await user.create_confirmation_token(-1)
        response = client.post(
            "/api/auth/confirm_account",
            params={"token": token},
        )

        assert response.status_code == 422
        assert "Expired token" in response.text

    async def test_user_confirmation_success(self, db: AsyncSQLAlchemyWrapper, client: TestClient):
        async with db.scoped_session() as session:
            user = await User.get_by(session, username=operator.username)
        assert user.confirmed_at is None

        token = await user.create_confirmation_token()
        response = client.post(
            "/api/auth/confirm_account",
            params={"token": token},
        )

        assert response.status_code == 200
        assert "Your account has been confirmed" in response.text

        async with db.scoped_session() as session:
            user = await User.get_by(session, username=operator.username)
        assert user.is_confirmed


@pytest.mark.asyncio
class TestUserResetPassword(UsersAware):
    async def test_user_reset_password_token_expired(self, db: AsyncSQLAlchemyWrapper, client: TestClient):
        # User need to be confirmed to update his password
        async with db.scoped_session() as session:
            await User.update(session, user_id=operator.id, values={"confirmed_at": datetime.now()})
            user = await User.get_by(session, username=operator.username)
        assert user.is_confirmed

        token = await user.create_password_reset_token(-1)
        response = client.post(
            "/api/auth/reset_password",
            params={"token": token},
            json={"password": "new_password"},
        )

        assert response.status_code == 422
        assert "Expired token" in response.text

    async def test_user_reset_password_token_wrong_format(self, db: AsyncSQLAlchemyWrapper, client: TestClient):
        # User need to be confirmed to update his password
        async with db.scoped_session() as session:
            await User.update(session, user_id=operator.id, values={"confirmed_at": datetime.now()})
            user = await User.get_by(session, username=operator.username)
        assert user.is_confirmed

        token = await user.create_password_reset_token()
        response = client.post(
            "/api/auth/reset_password",
            params={"token": token},
            json={"password": "new_password"},
        )

        assert response.status_code == 400
        assert "Wrong password format" in response.text

    async def test_user_reset_password_token_success(self, db: AsyncSQLAlchemyWrapper, client: TestClient):
        # User need to be confirmed to update his password
        async with db.scoped_session() as session:
            await User.update(session, user_id=operator.id, values={"confirmed_at": datetime.now()})
            user = await User.get_by(session, username=operator.username)
        assert user.is_confirmed

        old_hash = user.password_hash

        token = await user.create_password_reset_token()
        response = client.post(
            "/api/auth/reset_password",
            params={"token": token},
            json={"password": "New_val1d_password!"},
        )

        assert response.status_code == 200
        assert "Your password has been changed" in response.text

        async with db.scoped_session() as session:
            user = await User.get_by(session, username=operator.username)
        assert user.password_hash != old_hash


class TestRegistrationToken(UsersAware):
    def test_registration_token_failure(self, client: TestClient):
        response = client.post("/api/auth/registration_token")
        assert response.status_code == 403

    def test_registration_token_success(self, client_admin: TestClient):
        response = client_admin.post("/api/auth/registration_token")
        assert response.status_code == 200

        data = json.loads(response.text)
        payload = Tokenizer.loads(data)
        assert payload["sub"] == TOKEN_SUBS.REGISTRATION.value
        assert not payload.get("role", None)

    def test_registration_token_user_info(self, client_admin: TestClient):
        username = "BoringTest"
        role = "User"
        response = client_admin.post(
            "/api/auth/registration_token",
            json={
                "username": username,
                "role": role,
            }
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        payload = Tokenizer.loads(data)
        assert not payload.get("role")
        assert payload["username"] == username

    def test_registration_token_operator_info(self, client_admin: TestClient):
        role = "Operator"
        response = client_admin.post(
            "/api/auth/registration_token",
            json={
                "role": role,
            }
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        payload = Tokenizer.loads(data)
        assert payload["role"] == role
