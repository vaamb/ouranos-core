from datetime import timedelta

from fastapi.testclient import TestClient

from ouranos import json

from ...data.gaia import *


def test_sensor(client: TestClient):
    response = client.get(
        "/api/gaia/sensor",
        params={"current_data": True, "historic_data": True}
    )
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    # Most data is the same as the one given by hardware, focus on the difference
    current_data = data["data"]["current"][0]
    assert current_data["measure"] == measure_record["measure"]
    current_value = current_data["values"][0]
    assert current_value[0] == sensors_data["timestamp"].isoformat()
    assert current_value[1] == measure_record["value"]

    historic_data = data["data"]["historic"][0]
    assert historic_data["measure"] == measure_record["measure"]
    historic_value = historic_data["values"][0]
    assert historic_value[0] == (sensors_data["timestamp"] - timedelta(hours=1)).isoformat()
    assert historic_value[1] == measure_record["value"]


def test_measures_available(client: TestClient):
    response = client.get("/api/gaia/sensor/measures_available")
    assert response.status_code == 200


def test_hardware_unique(client: TestClient):
    response = client.get(
        f"/api/gaia/sensor/u/{hardware_uid}",
        params={"current_data": True, "historic_data": True}
    )  # The only hardware added is a sensor
    assert response.status_code == 200

    data = json.loads(response.text)
    # Most data is the same as the one given by hardware, focus on the difference
    current_data = data["data"]["current"][0]
    assert current_data["measure"] == measure_record["measure"]
    current_value = current_data["values"][0]
    assert current_value[0] == sensors_data["timestamp"].isoformat()
    assert current_value[1] == measure_record["value"]

    historic_data = data["data"]["historic"][0]
    assert historic_data["measure"] == measure_record["measure"]
    historic_value = historic_data["values"][0]
    assert historic_value[0] == (sensors_data["timestamp"] - timedelta(hours=1)).isoformat()
    assert historic_value[1] == measure_record["value"]


def test_hardware_unique_current(client: TestClient):
    response = client.get(f"/api/gaia/sensor/u/{hardware_uid}/data/current")  # The only hardware added is a sensor
    assert response.status_code == 200

    current_data = json.loads(response.text)[0]
    # Most data is the same as the one given by hardware, focus on the difference
    assert current_data["measure"] == measure_record["measure"]
    current_value = current_data["values"][0]
    assert current_value[0] == sensors_data["timestamp"].isoformat()
    assert current_value[1] == measure_record["value"]


def test_hardware_unique_historic(client: TestClient):
    response = client.get(f"/api/gaia/sensor/u/{hardware_uid}/data/historic")  # The only hardware added is a sensor
    assert response.status_code == 200

    historic_data = json.loads(response.text)[0]
    # Most data is the same as the one given by hardware, focus on the difference
    assert historic_data["measure"] == measure_record["measure"]
    current_value = historic_data["values"][0]
    assert current_value[0] == (sensors_data["timestamp"] - timedelta(hours=1)).isoformat()
    assert current_value[1] == measure_record["value"]
