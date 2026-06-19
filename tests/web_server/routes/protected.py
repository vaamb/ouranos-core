from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.config.consts import LOGIN_NAME
from ouranos.core.database.models.app import User
from ouranos.web_server.auth import SessionInfo

from tests.data.auth import operator
from tests.class_fixtures import UsersAware


class TestAuthenticatedProtection(UsersAware):
    def test_access_auth_from_anon(self, client: TestClient):
        response = client.get("/api/tests/is_authenticated")
        assert response.status_code == 403

    def test_access_auth_from_user(self, client_user: TestClient):
        response = client_user.get("/api/tests/is_authenticated")
        assert response.status_code == 200
        assert response.text == '"Success"'

    def test_access_auth_from_operator(self, client_operator: TestClient):
        response = client_operator.get("/api/tests/is_authenticated")
        assert response.status_code == 200
        assert response.text == '"Success"'

    def test_access_auth_from_admin(self, client_admin: TestClient):
        response = client_admin.get("/api/tests/is_authenticated")
        assert response.status_code == 200
        assert response.text == '"Success"'


class TestOperatorProtection(UsersAware):
    def test_access_operator_from_anon(self, client: TestClient):
        response = client.get("/api/tests/is_operator")
        assert response.status_code == 403

    def test_access_operator_from_user(self, client_user: TestClient):
        response = client_user.get("/api/tests/is_operator")
        assert response.status_code == 403

    def test_access_operator_from_operator(self, client_operator: TestClient):
        response = client_operator.get("/api/tests/is_operator")
        assert response.status_code == 200
        assert response.text == '"Success"'

    def test_access_operator_from_admin(self, client_admin: TestClient):
        response = client_admin.get("/api/tests/is_operator")
        assert response.status_code == 200
        assert response.text == '"Success"'


class TestAdminProtection(UsersAware):
    def test_access_admin_from_anon(self, client: TestClient):
        response = client.get("/api/tests/is_admin")
        assert response.status_code == 403

    def test_access_admin_from_user(self, client_user: TestClient):
        response = client_user.get("/api/tests/is_admin")
        assert response.status_code == 403

    def test_access_admin_from_operator(self, client_operator: TestClient):
        response = client_operator.get("/api/tests/is_admin")
        assert response.status_code == 403

    def test_access_admin_from_admin(self, client_admin: TestClient):
        response = client_admin.get("/api/tests/is_admin")
        assert response.status_code == 200
        assert response.text == '"Success"'


class TestBearerTokenProtection(UsersAware):
    # The gates must enforce roles identically whether the session token is
    # carried in the cookie (browser) or the `Authorization` header (API client)

    def test_access_via_bearer_token(self, client: TestClient):
        # Mints the same session token as the login cookie, but carried in the
        # `Authorization: Bearer ...` header instead (the non-browser auth path)
        token = SessionInfo(id="session_id", user_id=operator.id, remember=True).to_token()
        headers = {LOGIN_NAME.HEADER.value: f"Bearer {token}"}

        response = client.get("/api/tests/is_operator", headers=headers)
        assert response.status_code == 200
        assert response.text == '"Success"'

    def test_access_with_malformed_bearer_token(self, client: TestClient):
        response = client.get(
            "/api/tests/is_authenticated",
            headers={LOGIN_NAME.HEADER.value: "Bearer not.a.real.token"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestInactiveUserProtection(UsersAware):
    async def test_inactive_user_treated_as_anonymous(
            self,
            db: AsyncSQLAlchemyWrapper,
            client_operator: TestClient,
    ):
        # A deactivated account is demoted to anonymous by `load_user`, so a
        # valid session no longer grants access to a protected resource
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=operator.id, values={"active": False})

        response = client_operator.get("/api/tests/is_authenticated")
        assert response.status_code == 403
