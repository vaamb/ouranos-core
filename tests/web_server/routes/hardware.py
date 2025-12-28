from fastapi.testclient import TestClient
import pytest

import gaia_validators as gv

from ouranos import json

import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher
from tests.class_fixtures import HardwareAware, UsersAware


class TestHardware(HardwareAware, UsersAware):
    def test_hardware(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/hardware")
        assert response.status_code == 200

        data = json.loads(response.text)[0]
        assert data["uid"] == g_data.hardware_data["uid"]
        assert data["name"] == g_data.hardware_data["name"]
        assert data["address"] == g_data.hardware_data["address"]
        assert data["type"] == g_data.hardware_data["type"]
        assert data["level"] == g_data.hardware_data["level"]
        assert data["model"] == g_data.hardware_data["model"]
        assert data["measures"][0] == {
            "name": "temperature",
            "unit": "°C"
        }
        # TODO: re enable by linking Hardware to Plant
        #assert data["plants"] == g_data.hardware_data["plants"]

    def test_hardware_models(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/hardware/models_available")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 0

    def test_hardware_creation_request_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = {
            "name": "TestLight",
            "address": "GPIO_17",
            "level": gv.HardwareLevel.environment.name,
            "type": gv.HardwareType.light.name,
            "model": "LedPanel",
        }
        response = client_operator.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.create
        assert dispatched["data"]["target"] == "hardware"
        assert dispatched["data"]["data"]["name"] == payload["name"]

    def test_hardware_unique(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["uid"] == g_data.hardware_data["uid"]
        assert data["name"] == g_data.hardware_data["name"]
        assert data["address"] == g_data.hardware_data["address"]
        assert data["type"] == g_data.hardware_data["type"]
        assert data["level"] == g_data.hardware_data["level"]
        assert data["model"] == g_data.hardware_data["model"]
        assert data["measures"][0] == {
            "name": "temperature",
            "unit": "°C"
        }
        # Test groups
        data["groups"].sort()
        assert "__type__" not in data["groups"]
        groups_data = [*g_data.hardware_data["groups"]]
        groups_data.sort()
        if "__type__" in groups_data:
            groups_data[groups_data.index("__type__")] = g_data.hardware_data["type"]
        assert data["groups"] == groups_data
        # TODO: re enable by linking Hardware to Plant
        #assert data["plants"] == g_data.hardware_data["plants"]

    def test_hardware_unique_wrong_uid(self, client: TestClient):
        response = client.get(
            "/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/wrong_id")
        assert response.status_code == 404

    def test_hardware_update_request_failure_user(self, client_user: TestClient):
        response = client_user.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 403

    def test_hardware_update_request_failure_payload(self, client_operator: TestClient):
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 422

    def test_hardware_update_request_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = {
            "name": "TestLedLight",
            "address": "GPIO_37",
        }
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.update
        assert dispatched["data"]["target"] == "hardware"
        assert dispatched["data"]["data"]["name"] == payload["name"]
        with pytest.raises(KeyError):
            dispatched["data"]["data"]["level"]  # Not in the payload, should be missing

    def test_hardware_delete_request_failure_user(self, client_user: TestClient):
        response = client_user.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 403

    def test_hardware_delete_request_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        response = client_operator.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.delete
        assert dispatched["data"]["target"] == "hardware"
        assert dispatched["data"]["data"] == g_data.hardware_uid
