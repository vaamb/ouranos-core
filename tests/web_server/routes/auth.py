from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from httpx import BasicAuth
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.config.consts import LOGIN_NAME, SESSION_FRESHNESS, TOKEN_SUBS
from ouranos.core.database.models.app import anonymous_user, User
from ouranos.core.utils import Tokenizer
from ouranos.web_server.user_session import SessionInfo

from tests.data.auth import admin, operator
from tests.class_fixtures import UsersAware


registration_payload = {
    "username": "NewUser",
    "password": "Password1!",
    "email": "new_user@fakemail.com",
}


def utc_now_second() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def session_cookie(session_info: SessionInfo) -> dict[str, str]:
    return {LOGIN_NAME.COOKIE.value: session_info.to_token()}


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


@pytest.mark.asyncio
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

    def test_update_current_user_anonymous(self, client: TestClient):
        # Anonymous users are a no-op, signalled by a 204 (no content)
        response = client.put("/api/auth/current_user")
        assert response.status_code == 204

    async def test_update_current_user_admin(
            self,
            db: AsyncSQLAlchemyWrapper,
            client_admin: TestClient,
    ):
        old_last_seen = datetime(2000, 1, 1, tzinfo=timezone.utc)
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=admin.id, values={"last_seen": old_last_seen})

        response = client_admin.put("/api/auth/current_user")
        assert response.status_code == 200

        async with db.scoped_session() as session:
            user = await User.get_by(session, username=admin.username)
        assert user.last_seen > old_last_seen


class TestExtendSession(UsersAware):
    def test_extend_session_anonymous(self, client: TestClient):
        # Anonymous users have no session to refresh, signalled by a 204
        response = client.get("/api/auth/extend_session")
        assert response.status_code == 204

    def test_extend_session_authenticated(self, client_admin: TestClient):
        response = client_admin.get("/api/auth/extend_session")
        assert response.status_code == 200


@pytest.mark.asyncio
class TestRefreshSession(UsersAware):
    """`/auth/refresh_session` re-issues the cookie with a new "iat"."""

    @staticmethod
    async def stale_cookie(
            db: AsyncSQLAlchemyWrapper,
            client: TestClient,
    ) -> SessionInfo:
        stale_iat = utc_now_second() - timedelta(seconds=SESSION_FRESHNESS + 60)
        async with db.scoped_session() as session:
            await User.update(
                session,
                user_id=admin.id,
                values={"sessions_valid_from": stale_iat - timedelta(hours=1)},
            )
        stale = SessionInfo(user_id=admin.id, iat=stale_iat, remember=True)
        assert not stale.is_fresh

        client.cookies = session_cookie(stale)
        return stale

    def test_refresh_session_failure_anonymous(self, client: TestClient):
        # There is no session to refresh, and no cookie to prove who the caller is
        response = client.get(
            "/api/auth/refresh_session",
            auth=BasicAuth(admin.username, admin.password),
        )
        assert response.status_code == 401
        assert LOGIN_NAME.COOKIE.value not in response.cookies

    async def test_refresh_session_failure_other_user_credentials(
            self,
            db: AsyncSQLAlchemyWrapper,
            client: TestClient,
    ):
        # Valid credentials only refresh the session they belong to
        stale = await self.stale_cookie(db, client)

        response = client.get(
            "/api/auth/refresh_session",
            auth=BasicAuth(operator.username, operator.password),
        )

        assert response.status_code == 401
        # No new cookie was issued: the admin session is still the stale one
        assert LOGIN_NAME.COOKIE.value not in response.cookies
        assert client.cookies[LOGIN_NAME.COOKIE.value] == stale.to_token()

    async def test_refresh_session_success(
            self,
            db: AsyncSQLAlchemyWrapper,
            client: TestClient,
    ):
        stale = await self.stale_cookie(db, client)
        # The stale cookie authenticates, but is refused by the freshness guard
        assert client.post("/api/auth/revoke_sessions").status_code == 401

        response = client.get(
            "/api/auth/refresh_session",
            auth=BasicAuth(admin.username, admin.password),
        )
        assert response.status_code == 200

        refreshed = SessionInfo.from_token(response.cookies[LOGIN_NAME.COOKIE.value])
        assert refreshed.iat > stale.iat
        assert refreshed.is_fresh
        # Only "iat" moved: refreshing is not a way to extend the session's life
        assert refreshed.exp == stale.exp

        # The freshness guard now lets the same caller through
        client.cookies = session_cookie(refreshed)
        assert client.post("/api/auth/revoke_sessions").status_code == 200


@pytest.mark.asyncio
class TestRevokeSessions(UsersAware):
    """`/auth/revoke_sessions` invalidates every session the user holds.

    It is the "log out everywhere" counterpart to `/auth/logout`
    """

    def test_revoke_sessions_anonymous(self, client: TestClient):
        # An anonymous caller has no fresh cookie and is told to login first
        response = client.post("/api/auth/revoke_sessions")
        assert response.status_code == 401

    async def test_revoke_sessions_stale_session(
            self,
            db: AsyncSQLAlchemyWrapper,
            client: TestClient,
    ):
        stale_iat = utc_now_second() - timedelta(seconds=SESSION_FRESHNESS + 60)
        async with db.scoped_session() as session:
            await User.update(
                session,
                user_id=admin.id,
                values={"sessions_valid_from": stale_iat - timedelta(hours=1)},
            )
        stale = SessionInfo(user_id=admin.id, iat=stale_iat, remember=True)
        assert not stale.is_fresh

        client.cookies = session_cookie(stale)
        response = client.post("/api/auth/revoke_sessions")

        assert response.status_code == 401

    async def test_revoke_sessions_after_validity(
            self,
            db: AsyncSQLAlchemyWrapper,
            client_admin: TestClient,
    ):
        previous_cutoff = utc_now_second() - timedelta(days=1)
        async with db.scoped_session() as session:
            await User.update(
                session,
                user_id=admin.id,
                values={"sessions_valid_from": previous_cutoff},
            )

        response = client_admin.post("/api/auth/revoke_sessions")

        assert response.status_code == 200
        async with db.scoped_session() as session:
            user = await User.get(session, admin.id)

        assert user is not None

        assert user.sessions_valid_from > previous_cutoff

        # Verify the cookie was removed
        set_cookie_header = response.headers["set-cookie"]
        assert LOGIN_NAME.COOKIE.value in set_cookie_header
        assert "Max-Age=0" in set_cookie_header

    async def test_revoked_token_no_longer_authenticates(
            self,
            db: AsyncSQLAlchemyWrapper,
            client: TestClient,
    ):
        # Verify that fresh but invalidated token returns an anonymous user
        async with db.scoped_session() as session:
            await User.update(
                session,
                user_id=admin.id,
                values={"sessions_valid_from": utc_now_second() - timedelta(days=1)},
            )

        session_info = SessionInfo(
            user_id=admin.id,
            iat=utc_now_second() - timedelta(seconds=60),
            remember=True,
        )
        client.cookies = session_cookie(session_info)
        assert client.post("/api/auth/revoke_sessions").status_code == 200

        client.cookies = session_cookie(session_info)
        response = client.get("/api/auth/current_user")

        assert response.status_code == 200
        assert json.loads(response.text)["id"] == anonymous_user.id


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

    def test_registration_token_failure_invalid_role(self, client_admin: TestClient):
        response = client_admin.post(
            "/api/auth/registration_token",
            json={
                "role": "NotARealRole",
            }
        )
        assert response.status_code == 422
        assert "Invalid role" in response.text

    def test_registration_token_failure_email_required(self, client_admin: TestClient):
        # Asking to send the invitation email without providing an address fails
        response = client_admin.post(
            "/api/auth/registration_token",
            params={"send_email": True},
        )
        assert response.status_code == 422
        assert "Email address is required" in response.text
