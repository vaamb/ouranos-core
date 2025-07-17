from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from ouranos import json
from ouranos.core.config.consts import START_TIME

import tests.data.system as g_data
from tests.web_server.class_fixtures import SystemAware, UsersAware


class TestSystem(SystemAware, UsersAware):
    def test_route_anonymous(self, client: TestClient):
        server_uid = g_data.system_dict["uid"]
        response = client.get(f"/api/system/{server_uid}")
        assert response.status_code == 403

    def test_unique_system(self, client_admin: TestClient):
        server_uid = g_data.system_dict["uid"]
        response = client_admin.get(f"/api/system/{server_uid}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert datetime.fromisoformat(data["start_time"]) == START_TIME
        assert data["uid"] == g_data.system_dict["uid"]
        assert data["hostname"] == g_data.system_dict["hostname"]
        assert data["RAM_total"] == g_data.system_dict["RAM_total"]
        assert data["DISK_total"] == g_data.system_dict["DISK_total"]

    def test_current_data(self, client_admin: TestClient):
        server_uid = g_data.system_dict["uid"]
        response = client_admin.get(f"/api/system/{server_uid}/data/current")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["order"] == [
            "timestamp", "CPU_used", "CPU_temp", "RAM_process", "RAM_used",
            "DISK_used"
        ]
        value = data["values"][0]
        assert datetime.fromisoformat(value[0]) == g_data.system_data_dict["timestamp"]
        assert value[1] == g_data.system_data_dict["CPU_used"]
        assert value[2] == g_data.system_data_dict["CPU_temp"]
        assert value[3] == g_data.system_data_dict["RAM_process"]
        assert value[4] == g_data.system_data_dict["RAM_used"]
        assert value[5] == g_data.system_data_dict["DISK_used"]

    def test_historic_data(self, client_admin: TestClient):
        server_uid = g_data.system_dict["uid"]
        response = client_admin.get(f"/api/system/{server_uid}/data/historic")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["order"] == [
            "timestamp", "CPU_used", "CPU_temp", "RAM_process", "RAM_used",
            "DISK_used"
        ]
        value = data["values"][0]
        assert datetime.fromisoformat(value[0]) == (g_data.system_data_dict["timestamp"] - timedelta(hours=1))
        assert value[1] == g_data.system_data_dict["CPU_used"]
        assert value[2] == g_data.system_data_dict["CPU_temp"]
        assert value[3] == g_data.system_data_dict["RAM_process"]
        assert value[4] == g_data.system_data_dict["RAM_used"]
        assert value[5] == g_data.system_data_dict["DISK_used"]
