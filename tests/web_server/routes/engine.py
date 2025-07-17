from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import Engine

import tests.data.gaia as g_data
from tests.web_server.class_fixtures import EngineAware, UsersAware


@pytest.mark.asyncio
class TestEngineCore(EngineAware, UsersAware):
    async def test_engines(
            self,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client.get("/api/gaia/engine")
        assert response.status_code == 200
        data = json.loads(response.text)

        async with db.scoped_session() as session:
            engines = await Engine.get_multiple_by_id(session, engines_id=None)
            assert data[0]["uid"] == engines[0].uid
            assert data[0]["address"] == engines[0].address
            assert len(data[0]["ecosystems"]) == 0

    @pytest.mark.asyncio
    async def test_engine_unique(
            self,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client.get(f"/api/gaia/engine/u/{g_data.engine_uid}")
        assert response.status_code == 200
        data = json.loads(response.text)

        async with db.scoped_session() as session:
            engine = await Engine.get(session, uid=g_data.engine_uid)
            assert data["uid"] == engine.uid
            assert data["address"] == engine.address
            assert len(data["ecosystems"]) == 0

    def test_engine_unique_wrong_id(self, client: TestClient):
        response = client.get("/api/gaia/engine/u/wrong_id")
        assert response.status_code == 404

    def test_engine_delete_request_failure_anon(self, client: TestClient):
        response = client.delete(f"/api/gaia/engine/u/{g_data.engine_uid}")
        assert response.status_code == 403

    def test_engine_delete_request_failure_not_found(self, client_operator: TestClient):
        engine_uid = "wrong_id"
        response = client_operator.delete(f"/api/gaia/engine/u/{engine_uid}")
        assert response.status_code == 404

    def test_engine_delete_request_success(self, client_operator: TestClient):
        response = client_operator.delete(f"/api/gaia/engine/u/{g_data.engine_uid}")
        assert response.status_code == 202
