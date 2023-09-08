from fastapi.testclient import TestClient

from ouranos import json

import tests.data.gaia as g_data


def test_warning_failure_anon(client: TestClient):
    response = client.get("/api/gaia/warning")
    assert response.status_code == 403


def test_warning_success(client_user: TestClient):
    response = client_user.get("/api/gaia/warning")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data[0]["level"] == 0
    assert data[0]["title"] == g_data.gaia_warning["title"]
    assert data[0]["description"] == g_data.gaia_warning["description"]
