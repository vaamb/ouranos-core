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

        data = json.loads(response.text)
        # The fixture registers two pieces of hardware: a sensor and a camera
        assert len(data) == 2
        by_uid = {h["uid"]: h for h in data}
        assert set(by_uid) == {g_data.hardware_data["uid"], g_data.camera_config["uid"]}

        hardware = by_uid[g_data.hardware_data["uid"]]
        assert hardware["ecosystem_uid"] == g_data.ecosystem_uid
        assert hardware["name"] == g_data.hardware_data["name"]
        assert hardware["address"] == g_data.hardware_data["address"]
        assert hardware["type"] == g_data.hardware_data["type"]
        assert hardware["level"] == g_data.hardware_data["level"]
        assert hardware["model"] == g_data.hardware_data["model"]
        assert hardware["measures"][0] == {
            "name": "temperature",
            "unit": "°C"
        }
        # TODO: re enable by linking Hardware to Plant
        #assert hardware["plants"] == g_data.hardware_data["plants"]

    def test_hardware_filter_by_uid(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/hardware?hardware_uid={g_data.hardware_uid}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["uid"] == g_data.hardware_uid

    def test_hardware_filter_by_type(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/hardware?hardware_type={gv.HardwareType.sensor.value}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["uid"] == g_data.hardware_uid
        assert data[0]["type"] == gv.HardwareType.sensor.name

    def test_hardware_filter_by_level(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/hardware"
            f"?hardware_level={gv.HardwareLevel.ecosystem.value}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["uid"] == g_data.camera_config["uid"]

    def test_hardware_filter_by_model(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/hardware"
            f"?hardware_model={g_data.hardware_data['model']}")
        assert response.status_code == 200

        data = json.loads(response.text)
        # Both fixtures share the same model
        assert len(data) == 2

        response = client.get(
            "/api/gaia/ecosystem/hardware?hardware_model=does_not_exist")
        assert response.status_code == 200
        assert json.loads(response.text) == []

    def test_hardware_types_available(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/hardware/types_available")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == len(gv.HardwareType.__members__)
        assert {"name": "sensor", "value": gv.HardwareType.sensor.value} in data

    def test_hardware_models(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/hardware/models_available")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 0

    def test_hardware_creation_request_failure_user(self, client_user: TestClient):
        response = client_user.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u")
        assert response.status_code == 403

    def test_hardware_creation_request_wrong_ecosystem(
            self,
            client_operator: TestClient,
    ):
        payload = {
            "name": "TestLight",
            "address": "GPIO_17",
            "level": gv.HardwareLevel.environment.name,
            "type": gv.HardwareType.light.name,
            "model": "LedPanel",
        }
        response = client_operator.post(
            "/api/gaia/ecosystem/u/wrong_uid/hardware/u",
            json=payload,
        )
        assert response.status_code == 404

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
        assert dispatched["data"]["kwargs"]["name"] == payload["name"]

    def test_ecosystem_hardware(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 2
        assert {h["uid"] for h in data} == \
               {g_data.hardware_data["uid"], g_data.camera_config["uid"]}

    def test_ecosystem_hardware_filter_by_type(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware"
            f"?hardware_type={gv.HardwareType.camera.value}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["uid"] == g_data.camera_config["uid"]

    def test_ecosystem_hardware_wrong_ecosystem(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/u/wrong_uid/hardware")
        assert response.status_code == 404

    def test_hardware_unique(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 200

        data = json.loads(response.text)
        input_data = gv.HardwareConfig(**g_data.hardware_data)
        assert data["uid"] == input_data.uid
        assert data["name"] == input_data.name
        assert data["address"] == input_data.address
        assert data["type"] == input_data.type.name
        assert data["level"] == input_data.level
        assert data["model"] == input_data.model
        # Test measures
        assert sorted(data["measures"]) == \
               sorted({"name": m.name, "unit": m.unit} for m in input_data.measures)
        # Test groups
        assert sorted(data["groups"]) == sorted(input_data.groups)
        assert "__type__" not in data["groups"]

        # TODO: re enable by linking Hardware to Plant
        #assert data["plants"] == g_data.hardware_data["plants"]

    def test_hardware_unique_wrong_ecosystem(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/wrong_uid/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 404

    def test_hardware_unique_wrong_uid(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/wrong_id")
        assert response.status_code == 404

    def test_hardware_update_request_failure_user(self, client_user: TestClient):
        response = client_user.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 403

    def test_hardware_update_request_failure_payload(self, client_operator: TestClient):
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 422

    def test_hardware_update_request_wrong_uid(self, client_operator: TestClient):
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/wrong_id",
            json={"name": "TestLedLight"},
        )
        assert response.status_code == 404

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
        assert dispatched["data"]["kwargs"]["name"] == payload["name"]
        assert dispatched["data"]["kwargs"]["uid"] == g_data.hardware_uid
        with pytest.raises(KeyError):
            dispatched["data"]["kwargs"]["level"]  # Not in the payload, should be missing

    def test_hardware_delete_request_failure_user(self, client_user: TestClient):
        response = client_user.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/{g_data.hardware_uid}")
        assert response.status_code == 403

    def test_hardware_delete_request_wrong_uid(self, client_operator: TestClient):
        response = client_operator.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/hardware/u/wrong_id")
        assert response.status_code == 404

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
        assert dispatched["data"]["kwargs"]["uid"] == g_data.hardware_uid
