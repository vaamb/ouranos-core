from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.config.consts import START_TIME
from ouranos.core.database.models.memory import SystemDbCache
from ouranos.core.database.models.system import SystemRecord
from ouranos.core.utils import create_time_window


def test_route_anonymous(client: TestClient):
    response = client.get("/api/system/start_time")
    assert response.status_code == 403


def test_start_time(client_admin: TestClient):
    response = client_admin.get("/api/system/start_time")
    assert response.status_code == 200
    data = json.loads(response.text)
    assert data == START_TIME.isoformat()


@pytest.mark.asyncio
async def test_current_data(
        client_admin: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client_admin.get("/api/system/data/current")
    assert response.status_code == 200
    data = json.loads(response.text)

    async with db.scoped_session() as session:
        current_data = await SystemDbCache.get_recent(session)
        assert data[0]["timestamp"] == current_data[0].timestamp.isoformat()
        assert data[0]["CPU_temp"] == current_data[0].CPU_temp


@pytest.mark.asyncio
async def test_historic_data(
        client_admin: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client_admin.get("/api/system/data/historic")
    assert response.status_code == 200
    data = json.loads(response.text)

    async with db.scoped_session() as session:
        time_window = create_time_window()
        historic_data = await SystemRecord.get_records(session, time_window)
        historic = historic_data[0]
        assert data["records"][0][0] == historic.timestamp.isoformat()
        assert data["records"][0][2] == historic_data[0].CPU_temp
