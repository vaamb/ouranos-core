from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

import gaia_validators as gv

from ouranos import json
from ouranos.core.database.models.gaia import CrudRequest, Engine

import tests.data.gaia as g_data
from tests.class_fixtures import EcosystemAware, EngineAware, UsersAware


@pytest.mark.asyncio
class TestEngines(EngineAware):
    async def test_get(
            self,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client.get("/api/gaia/engine")
        assert response.status_code == 200
        data = json.loads(response.text)

        async with db.scoped_session() as session:
            engines = await Engine.get_multiple_by_id(session, engines_id=None)
        assert len(data) == 1

        engine = data[0]
        assert engine["uid"] == engines[0].uid
        assert engine["address"] == engines[0].address
        assert len(engine["ecosystems"]) == 0

    def test_get_filter_by_uid(self, client: TestClient):
        response = client.get(f"/api/gaia/engine?engines_id={g_data.engine_uid}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["uid"] == g_data.engine_uid

    def test_get_filter_by_unknown_uid(self, client: TestClient):
        response = client.get("/api/gaia/engine?engines_id=wrong_id")
        assert response.status_code == 200
        assert json.loads(response.text) == []


@pytest.mark.asyncio
class TestEngineUnique(EngineAware, UsersAware):
    async def test_get(
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

    def test_get_failure_wrong_id(self, client: TestClient):
        response = client.get("/api/gaia/engine/u/wrong_id")
        assert response.status_code == 404

    def test_delete_failure_anon(self, client: TestClient):
        response = client.delete(f"/api/gaia/engine/u/{g_data.engine_uid}")
        assert response.status_code == 403

    def test_delete_failure_wrong_id(self, client_operator: TestClient):
        response = client_operator.delete("/api/gaia/engine/u/wrong_id")
        assert response.status_code == 404

    def test_delete_success(self, client_operator: TestClient):
        response = client_operator.delete(f"/api/gaia/engine/u/{g_data.engine_uid}")
        assert response.status_code == 202

        # The engine is now gone
        response = client_operator.get(f"/api/gaia/engine/u/{g_data.engine_uid}")
        assert response.status_code == 404


@pytest.mark.asyncio
class TestEngineCrudRequests(EcosystemAware):
    async def _add_crud_request(self, db: AsyncSQLAlchemyWrapper) -> None:
        async with db.scoped_session() as session:
            await CrudRequest.create(
                session,
                uuid=uuid4(),
                values={
                    "engine_uid": g_data.engine_uid,
                    "ecosystem_uid": g_data.ecosystem_uid,
                    "action": gv.CrudAction.create,
                    "target": "hardware",
                },
            )

    async def test_get_empty(self, client: TestClient):
        response = client.get(
            f"/api/gaia/engine/u/{g_data.engine_uid}/crud_requests")
        assert response.status_code == 200
        assert json.loads(response.text) == []

    async def test_get(self, client: TestClient, db: AsyncSQLAlchemyWrapper):
        await self._add_crud_request(db)

        response = client.get(
            f"/api/gaia/engine/u/{g_data.engine_uid}/crud_requests")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        request = data[0]
        assert request["engine_uid"] == g_data.engine_uid
        assert request["ecosystem_uid"] == g_data.ecosystem_uid
        assert request["action"] == gv.CrudAction.create.name
        assert request["target"] == "hardware"
        assert request["completed"] is False

    def test_get_failure_wrong_engine(self, client: TestClient):
        response = client.get("/api/gaia/engine/u/wrong_id/crud_requests")
        assert response.status_code == 404
