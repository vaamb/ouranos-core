from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import GaiaWarning

import tests.data.gaia as g_data
from class_fixtures import GaiaWarningsAware, UsersAware


@pytest.mark.asyncio
class TestWarning(GaiaWarningsAware, UsersAware):
    def test_warning(self, client: TestClient):
        response = client.get("/api/gaia/warning")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data[0]["level"] == 0
        assert data[0]["title"] == g_data.gaia_warning["title"]
        assert data[0]["description"] == g_data.gaia_warning["description"]

    def test_warning_success_ecosystem(self, client_user: TestClient):
        response = client_user.get(
            "/api/gaia/warning",
            params={"ecosystem_uid": g_data.ecosystem_uid}
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data[0]["level"] == 0
        assert data[0]["title"] == g_data.gaia_warning["title"]
        assert data[0]["description"] == g_data.gaia_warning["description"]

    async def test_warning_mark_seen_success(
            self,
            client_user: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client_user.post("/api/gaia/warning/u/1/mark_as_seen")
        assert response.status_code == 202

        async with db.scoped_session() as session:
            warnings = await GaiaWarning.get_multiple(session)
            failed = True
            for warning in warnings:
                if warning.seen:
                    failed = False
                    break
            assert not failed

    async def test_warning_mark_solved_success(
            self,
            client_user: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client_user.post("/api/gaia/warning/u/1/mark_as_solved")
        assert response.status_code == 202

        async with db.scoped_session() as session:
            warnings = await GaiaWarning.get_multiple(session, show_solved=True)
            failed = True
            for warning in warnings:
                if warning.solved:
                    failed = False
                    break
            assert not failed
