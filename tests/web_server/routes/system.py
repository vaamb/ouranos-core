from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from ouranos import json
from ouranos.core.config.consts import START_TIME

import tests.data.system as g_data
from tests.class_fixtures import SystemAware, UsersAware


system_uid = g_data.system_dict["uid"]
data_order = [
    "timestamp", "CPU_used", "CPU_temp", "RAM_process", "RAM_used", "DISK_used"
]


class TestSystems(SystemAware, UsersAware):
    def test_get_failure_anon(self, client: TestClient):
        response = client.get("/api/system")
        assert response.status_code == 403

    def test_get_failure_not_admin(self, client_operator: TestClient):
        response = client_operator.get("/api/system")
        assert response.status_code == 403

    def test_get(self, client_admin: TestClient):
        response = client_admin.get("/api/system")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        system = data[0]
        assert datetime.fromisoformat(system["start_time"]) == START_TIME
        assert system["uid"] == g_data.system_dict["uid"]
        assert system["hostname"] == g_data.system_dict["hostname"]
        assert system["RAM_total"] == g_data.system_dict["RAM_total"]
        assert system["DISK_total"] == g_data.system_dict["DISK_total"]


class TestSystemUnique(SystemAware, UsersAware):
    def test_get_failure_anon(self, client: TestClient):
        response = client.get(f"/api/system/{system_uid}")
        assert response.status_code == 403

    def test_get_failure_not_admin(self, client_operator: TestClient):
        response = client_operator.get(f"/api/system/{system_uid}")
        assert response.status_code == 403

    def test_get(self, client_admin: TestClient):
        response = client_admin.get(f"/api/system/{system_uid}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert datetime.fromisoformat(data["start_time"]) == START_TIME
        assert data["uid"] == g_data.system_dict["uid"]
        assert data["hostname"] == g_data.system_dict["hostname"]
        assert data["RAM_total"] == g_data.system_dict["RAM_total"]
        assert data["DISK_total"] == g_data.system_dict["DISK_total"]

    def test_get_failure_wrong_uid(self, client_admin: TestClient):
        response = client_admin.get("/api/system/wrong_uid")
        assert response.status_code == 404

    def test_get_current_data(self, client_admin: TestClient):
        response = client_admin.get(f"/api/system/{system_uid}/data/current")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["order"] == data_order
        value = data["values"][0]
        assert datetime.fromisoformat(value[0]) == g_data.system_data_dict["timestamp"]
        assert value[1] == g_data.system_data_dict["CPU_used"]
        assert value[2] == g_data.system_data_dict["CPU_temp"]
        assert value[3] == g_data.system_data_dict["RAM_process"]
        assert value[4] == g_data.system_data_dict["RAM_used"]
        assert value[5] == g_data.system_data_dict["DISK_used"]

    def test_get_current_data_failure_wrong_uid(self, client_admin: TestClient):
        response = client_admin.get("/api/system/wrong_uid/data/current")
        assert response.status_code == 404

    def test_get_historic_data(self, client_admin: TestClient):
        response = client_admin.get(f"/api/system/{system_uid}/data/historic")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["order"] == data_order
        value = data["values"][0]
        assert datetime.fromisoformat(value[0]) == (
                g_data.system_data_dict["timestamp"] - timedelta(hours=1))
        assert value[1] == g_data.system_data_dict["CPU_used"]
        assert value[2] == g_data.system_data_dict["CPU_temp"]
        assert value[3] == g_data.system_data_dict["RAM_process"]
        assert value[4] == g_data.system_data_dict["RAM_used"]
        assert value[5] == g_data.system_data_dict["DISK_used"]

    def test_get_historic_data_failure_wrong_uid(self, client_admin: TestClient):
        response = client_admin.get("/api/system/wrong_uid/data/historic")
        assert response.status_code == 404
