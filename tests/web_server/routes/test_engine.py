from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import Engine

from ...data.gaia import *


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
    response = client.get(f"/api/gaia/engine/u/{engine_uid}")
    assert response.status_code == 200
    data = json.loads(response.text)

    async with db.scoped_session() as session:
        engine = await Engine.get(session, engine_uid)
        assert data["uid"] == engine.uid
        assert data["address"] == engine.address
        assert data["ecosystems"][0]["uid"] == engine.ecosystems[0].uid


@pytest.mark.asyncio
async def test_engine_unique_wrong_id(
        client: TestClient,
):
    response = client.get("/api/gaia/engine/u/wrong_id}")
    assert response.status_code == 404
