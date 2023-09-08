from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import Engine

import tests.data.gaia as g_data


@pytest.mark.asyncio
async def test_engines(
        client: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client.get("/api/gaia/engine")
    assert response.status_code == 200
    data = json.loads(response.text)

    async with db.scoped_session() as session:
        engines = await Engine.get_multiple(session)
        assert data[0]["uid"] == engines[0].uid
        assert data[0]["address"] == engines[0].address
        assert data[0]["ecosystems"][0]["uid"] == engines[0].ecosystems[0].uid


@pytest.mark.asyncio
async def test_engine_unique(
        client: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client.get(f"/api/gaia/engine/u/{g_data.engine_uid}")
    assert response.status_code == 200
    data = json.loads(response.text)

    async with db.scoped_session() as session:
        engine = await Engine.get(session, g_data.engine_uid)
        assert data["uid"] == engine.uid
        assert data["address"] == engine.address
        assert data["ecosystems"][0]["uid"] == engine.ecosystems[0].uid


def test_engine_unique_wrong_id(client: TestClient):
    response = client.get("/api/gaia/engine/u/wrong_id")
    assert response.status_code == 404


def test_engine_delete_request_failure_anon(client: TestClient):
    response = client.delete("/api/gaia/engine/u/{ecosystem_uid}")
    assert response.status_code == 403


def test_engine_delete_request_success(client_operator: TestClient):
    response = client_operator.delete(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}")
    assert response.status_code == 202
