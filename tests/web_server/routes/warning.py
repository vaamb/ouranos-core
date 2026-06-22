from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import GaiaWarning

import tests.data.gaia as g_data
from tests.class_fixtures import GaiaWarningsAware, UsersAware


@pytest.mark.asyncio
class TestWarning(GaiaWarningsAware, UsersAware):
    def test_get(self, client: TestClient):
        response = client.get("/api/gaia/warning")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["level"] == g_data.gaia_warning["level"]
        assert data[0]["title"] == g_data.gaia_warning["title"]
        assert data[0]["description"] == g_data.gaia_warning["description"]
        assert data[0]["created_by"] == g_data.ecosystem_uid
        # An unsolved warning has not been seen nor solved yet
        assert data[0]["seen_on"] is None
        assert data[0]["solved_on"] is None

    def test_get_filter_matching_ecosystem(self, client: TestClient):
        response = client.get(
            "/api/gaia/warning",
            params={"ecosystems_uid": g_data.ecosystem_uid},
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["title"] == g_data.gaia_warning["title"]

    def test_get_filter_other_ecosystem(self, client: TestClient):
        # The warning belongs to another ecosystem, so it is filtered out
        response = client.get(
            "/api/gaia/warning",
            params={"ecosystems_uid": "does_not_exist"},
        )
        assert response.status_code == 200
        assert json.loads(response.text) == []

    def test_get_filter_limit(self, client: TestClient):
        response = client.get("/api/gaia/warning", params={"limit": 0})
        assert response.status_code == 200
        assert json.loads(response.text) == []

    def test_mark_as_seen_failure_unauthorized(self, client: TestClient):
        response = client.post("/api/gaia/warning/u/1/mark_as_seen")
        assert response.status_code == 403

    async def test_mark_as_seen_success(
            self,
            client_user: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client_user.post("/api/gaia/warning/u/1/mark_as_seen")
        assert response.status_code == 202

        async with db.scoped_session() as session:
            warnings = await GaiaWarning.get_multiple(session)
            warning = next(w for w in warnings if w.id == 1)
            assert warning.seen
            assert not warning.solved

    def test_mark_as_solved_failure_unauthorized(self, client: TestClient):
        response = client.post("/api/gaia/warning/u/1/mark_as_solved")
        assert response.status_code == 403

    async def test_mark_as_solved_success(
            self,
            client_user: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client_user.post("/api/gaia/warning/u/1/mark_as_solved")
        assert response.status_code == 202

        async with db.scoped_session() as session:
            warnings = await GaiaWarning.get_multiple(session, show_solved=True)
            warning = next(w for w in warnings if w.id == 1)
            assert warning.solved
            # Marking a warning as solved also marks it as seen
            assert warning.seen

        # A solved warning no longer shows up in the default listing
        response = client_user.get("/api/gaia/warning")
        assert json.loads(response.text) == []

        # ... but can still be retrieved when explicitly requested
        response = client_user.get("/api/gaia/warning", params={"solved": True})
        assert len(json.loads(response.text)) == 1
