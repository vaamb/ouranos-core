from datetime import datetime

from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import User

from tests.data.auth import operator
from tests.class_fixtures import UsersAware


@pytest.mark.asyncio
class TestUser(UsersAware):
    def test_get_users_failure_anon(self, client: TestClient):
        response = client.get("/api/user")
        assert response.status_code == 403

    def test_get_users_failure_not_admin(self, client_operator: TestClient):
        response = client_operator.get("/api/user")
        assert response.status_code == 403

    def test_get_users_success(self, client_admin: TestClient):
        response = client_admin.get(
            "/api/user",
            params={
                "active": True,
            }
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 4  # Ouranos, user, operator and administrator

    def test_get_user_failure_different_user(self, client_operator: TestClient):
        response = client_operator.get("/api/user/u/Ouranos")
        assert response.status_code == 403

    def test_get_user_failure_not_found(self, client_admin: TestClient):
        # An admin passes the ownership check but the user does not exist
        response = client_admin.get("/api/user/u/NotAUser")
        assert response.status_code == 404

    def test_get_user_success_same_user(self, client_operator: TestClient):
        username = "Her"
        response = client_operator.get(f"/api/user/u/{username}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["username"] == username

    def test_get_user_success_admin(self, client_admin: TestClient):
        username = "Her"
        response = client_admin.get(f"/api/user/u/{username}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["username"] == username

    def test_update_user_failure_different_user(self, client_user: TestClient):
        payload = {"firstname": "Ouranos"}

        response = client_user.put(
            "/api/user/u/Ouranos",
            json=payload,
        )
        assert response.status_code == 403

    def test_update_user_failure_not_found(self, client_admin: TestClient):
        response = client_admin.put(
            "/api/user/u/NotAUser",
            json={"firstname": "Ghost"},
        )
        assert response.status_code == 404

    async def test_update_user_success_same_user(
            self,
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

    async def test_update_user_success_admin(
            self,
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

    def test_update_user_failure_other_admin(self, client_admin: TestClient):
        # The Ouranos system administrator has a permission level equal to the
        # admin's own, so it cannot be updated
        payload = {"firstname": "Ouranos"}

        response = client_admin.put(
            "/api/user/u/Ouranos",
            json=payload,
        )
        assert response.status_code == 403

    def test_confirmation_token_failure_anon(self, client: TestClient):
        response = client.get("/api/user/u/Her/confirmation_token")
        assert response.status_code == 403

    def test_confirmation_token_failure_different_user(self, client_user: TestClient):
        response = client_user.get("/api/user/u/Her/confirmation_token")
        assert response.status_code == 403

    async def test_confirmation_token_success(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        # A not-yet-confirmed user can mint a confirmation token for itself
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=operator.id, values={"confirmed_at": None})

        response = client_operator.get("/api/user/u/Her/confirmation_token")
        assert response.status_code == 200
        assert json.loads(response.text)  # The bare token, as a JSON string

    async def test_confirmation_token_failure_already_confirmed(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=operator.id,
                values={"confirmed_at": datetime.now()})

        response = client_operator.get("/api/user/u/Her/confirmation_token")
        assert response.status_code == 409

    def test_password_reset_token_failure_anon(self, client: TestClient):
        response = client.get("/api/user/u/Her/password_reset_token")
        assert response.status_code == 403

    def test_password_reset_token_failure_different_user(self, client_user: TestClient):
        response = client_user.get("/api/user/u/Her/password_reset_token")
        assert response.status_code == 403

    async def test_password_reset_token_failure_not_confirmed(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        # A password can only be reset once the account has been confirmed
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=operator.id, values={"confirmed_at": None})

        response = client_operator.get("/api/user/u/Her/password_reset_token")
        assert response.status_code == 401

    async def test_password_reset_token_success(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        async with db.scoped_session() as session:
            await User.update(
                session, user_id=operator.id,
                values={"confirmed_at": datetime.now()})

        response = client_operator.get("/api/user/u/Her/password_reset_token")
        assert response.status_code == 200
        assert json.loads(response.text)  # The bare token, as a JSON string
