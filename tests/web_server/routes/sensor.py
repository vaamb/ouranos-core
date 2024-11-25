from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from ouranos import json

import tests.data.gaia as g_data


def test_measures_available(client: TestClient):
    response = client.get("/api/gaia/ecosystem/sensor/measures_available")
    assert response.status_code == 200


def test_current_data(client: TestClient):
    response = client.get("/api/gaia/ecosystem/sensor/data/current")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    assert data["uid"] == g_data.ecosystem_uid
    inner_data = data["values"][0]
    assert datetime.fromisoformat(inner_data["timestamp"]) == g_data.sensors_data["timestamp"]
    assert inner_data["sensor_uid"] == g_data.sensor_record.sensor_uid
    assert inner_data["measure"] == g_data.sensor_record.measure
    assert inner_data["value"] == g_data.sensor_record.value


def test_current_data_unique(client: TestClient):
    response = client.get(
        f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/sensor/data/current")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["uid"] == g_data.ecosystem_uid
    inner_data = data["values"][0]
    assert datetime.fromisoformat(inner_data["timestamp"]) == g_data.sensors_data["timestamp"]
    assert inner_data["sensor_uid"] == g_data.sensor_record.sensor_uid
    assert inner_data["measure"] == g_data.sensor_record.measure
    assert inner_data["value"] == g_data.sensor_record.value



def test_hardware_unique_current(client: TestClient):
    response = client.get(
        f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/sensor/u/{g_data.hardware_uid}"  # The only hardware added is a sensor
        f"/data/{g_data.sensor_record.measure}/current")
    assert response.status_code == 200

    current_data = json.loads(response.text)
    # Most data is the same as the one given by hardware, focus on the difference
    assert current_data["measure"] == g_data.sensor_record.measure
    current_value = current_data["values"][0]
    assert datetime.fromisoformat(current_value[0]) == g_data.sensors_data["timestamp"]
    assert current_value[1] == g_data.sensor_record.value


def test_hardware_unique_historic(client: TestClient):
    response = client.get(
        f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/sensor/u/{g_data.hardware_uid}"  # The only hardware added is a sensor
        f"/data/{g_data.sensor_record.measure}/historic")
    assert response.status_code == 200

    historic_data = json.loads(response.text)
    # Most data is the same as the one given by hardware, focus on the difference
    assert historic_data["measure"] == g_data.sensor_record.measure
    current_value = historic_data["values"][0]
    assert datetime.fromisoformat(current_value[0]) == \
           (g_data.sensors_data["timestamp"] - timedelta(hours=1))
    assert current_value[1] == g_data.sensor_record.value
