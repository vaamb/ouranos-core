from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from ouranos import json
from ouranos.core.config.consts import START_TIME

import tests.data.system as g_data


def test_route_anonymous(client: TestClient):
    response = client.get("/api/system/start_time")
    assert response.status_code == 403


def test_start_time(client_admin: TestClient):
    response = client_admin.get("/api/system/start_time")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert datetime.fromisoformat(data) == START_TIME


def test_current_data(client_admin: TestClient):
    response = client_admin.get("/api/system/data/current")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["order"] == [
        "timestamp", "system_uid", "CPU_used", "CPU_temp", "RAM_process",
        "RAM_used", "RAM_total", "DISK_used", "DISK_total"
    ]
    value = data["values"][0]
    assert datetime.fromisoformat(value[0]) == g_data.system_dict["timestamp"]
    assert value[1] == g_data.system_dict["system_uid"]
    assert value[2] == g_data.system_dict["CPU_used"]
    assert value[3] == g_data.system_dict["CPU_temp"]
    assert value[4] == g_data.system_dict["RAM_process"]
    assert value[5] == g_data.system_dict["RAM_used"]
    assert value[6] == g_data.system_dict["RAM_total"]
    assert value[7] == g_data.system_dict["DISK_used"]
    assert value[8] == g_data.system_dict["DISK_total"]


def test_historic_data(client_admin: TestClient):
    response = client_admin.get("/api/system/data/historic")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["order"] == [
        "timestamp", "system_uid", "CPU_used", "CPU_temp", "RAM_process",
        "RAM_used", "RAM_total", "DISK_used", "DISK_total"
    ]
    value = data["values"][0]
    assert datetime.fromisoformat(value[0]) == (g_data.system_dict["timestamp"] - timedelta(hours=1))
    assert value[1] == g_data.system_dict["system_uid"]
    assert value[2] == g_data.system_dict["CPU_used"]
    assert value[3] == g_data.system_dict["CPU_temp"]
    assert value[4] == g_data.system_dict["RAM_process"]
    assert value[5] == g_data.system_dict["RAM_used"]
    assert value[6] == g_data.system_dict["RAM_total"]
    assert value[7] == g_data.system_dict["DISK_used"]
    assert value[8] == g_data.system_dict["DISK_total"]
