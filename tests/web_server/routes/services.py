from fastapi.testclient import TestClient

from ouranos.core.database.models.app import Service

import pytest

@pytest.mark.asyncio
async def test_route_protection(client: TestClient, db):
    response = client.get("/api/app/services/weather/sun_times")
    assert response.status_code in (200, 204)

    response = client.put("/api/app/services/u/weather", json={"status": False})
    assert response == 200

    response = client.get("/api/app/services/weather/sun_times")
    assert response.status_code == 423

    response = client.put("/api/app/services/u/weather", json={"status": True})
    assert response == 200
