from fastapi.testclient import TestClient

from gaia_validators import HardwareLevel, HardwareType

from ouranos import json

from ...data.gaia import *


def test_hardware(client: TestClient):
    response = client.get("/api/gaia/hardware")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    assert data["uid"] == hardware_data["uid"]
    assert data["name"] == hardware_data["name"]
    assert data["address"] == hardware_data["address"]
    assert data["type"] == hardware_data["type"]
    assert data["level"] == hardware_data["level"]
    assert data["model"] == hardware_data["model"]
    assert data["measures"][0] == {
        "name": "temperature",
        "unit": "°C"
    }
    assert data["plants"] == hardware_data["plants"]


def test_hardware_models(client: TestClient):
    response = client.get("/api/gaia/hardware/models_available")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == 0


def test_hardware_creation_request_failure_user(client_user: TestClient):
    response = client_user.post("/api/gaia/ecosystem/u")
    assert response.status_code == 403


def test_hardware_creation_request_failure_payload(client_operator: TestClient):
    response = client_operator.post("/api/gaia/ecosystem/u")
    assert response.status_code == 422


def test_hardware_creation_request_success(client_operator: TestClient):
    payload = {
        "ecosystem_uid": ecosystem_uid,
        "name": "TestLight",
        "address": "GPIO_17",
        "level": HardwareLevel.environment.value,
        "type": HardwareType.light.value,
        "model": "LedPanel",
    }
    response = client_operator.post(
        "/api/gaia/hardware/u",
        json=payload,
    )
    assert response.status_code == 202


def test_hardware_unique(client: TestClient):
    response = client.get(f"/api/gaia/hardware/u/{hardware_uid}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["uid"] == hardware_data["uid"]
    assert data["name"] == hardware_data["name"]
    assert data["address"] == hardware_data["address"]
    assert data["type"] == hardware_data["type"]
    assert data["level"] == hardware_data["level"]
    assert data["model"] == hardware_data["model"]
    assert data["measures"][0] == {
        "name": "temperature",
        "unit": "°C"
    }
    assert data["plants"] == hardware_data["plants"]


def test_hardware_unique_wrong_uid(client: TestClient):
    response = client.get("/api/gaia/hardware/u/wrong_id")
    assert response.status_code == 404


def test_hardware_update_request_failure_user(client_user: TestClient):
    response = client_user.put(f"/api/gaia/hardware/u/{hardware_uid}")
    assert response.status_code == 403


def test_hardware_update_request_failure_payload(client_operator: TestClient):
    response = client_operator.put(f"/api/gaia/hardware/u/{hardware_uid}")
    assert response.status_code == 422


def test_hardware_update_request_success(client_operator: TestClient):
    payload = {
        "name": "TestLedLight",
        "address": "GPIO_37",
    }
    response = client_operator.put(
        f"/api/gaia/hardware/u/{hardware_uid}",
        json=payload,
    )
    assert response.status_code == 202


def test_hardware_delete_request_failure_user(client_user: TestClient):
    response = client_user.delete(f"/api/gaia/hardware/u/{hardware_uid}")
    assert response.status_code == 403


def test_hardware_delete_request_success(client_operator: TestClient):
    response = client_operator.delete(f"/api/gaia/hardware/u/{hardware_uid}")
    assert response.status_code == 202
