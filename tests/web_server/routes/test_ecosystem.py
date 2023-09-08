from datetime import datetime, time

from fastapi.testclient import TestClient
import pytest

from gaia_validators import ManagementConfig, ManagementFlags
from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import Ecosystem
from ouranos.core.utils import create_time_window

from ...data.gaia import *


# ------------------------------------------------------------------------------
#   Base ecosystem info
# ------------------------------------------------------------------------------
def test_ecosystems(client: TestClient):
    response = client.get("/api/gaia/ecosystem")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    assert data["uid"] == ecosystem_uid
    assert data["name"] == ecosystem_name
    assert data["engine_uid"] == engine_uid
    assert data["status"] == ecosystem_dict["status"]
    assert datetime.fromisoformat(data["registration_date"]) == ecosystem_dict["registration_date"]
    assert data["day_start"] == sky["day"].isoformat()
    assert data["night_start"] == sky["night"].isoformat()


def test_ecosystem_creation_request_failure_user(client_user: TestClient):
    response = client_user.post("/api/gaia/ecosystem/u")
    assert response.status_code == 403


def test_ecosystem_creation_request_failure_payload(client_operator: TestClient):
    response = client_operator.post("/api/gaia/ecosystem/u")
    assert response.status_code == 422


def test_ecosystem_creation_request_success(client_operator: TestClient):
    payload = {
        "name": "NewEcosystem",
        "engine_uid": engine_uid,
    }
    response = client_operator.post(
        "/api/gaia/ecosystem/u",
        json=payload,
    )
    assert response.status_code == 202


def test_ecosystem_unique(client: TestClient):
    response = client.get(f"/api/gaia/ecosystem/u/{ecosystem_uid}")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["uid"] == ecosystem_uid
    assert data["name"] == ecosystem_name
    assert data["engine_uid"] == engine_uid
    assert data["status"] == ecosystem_dict["status"]
    assert datetime.fromisoformat(data["registration_date"]) == ecosystem_dict["registration_date"]
    assert data["day_start"] == sky["day"].isoformat()
    assert data["night_start"] == sky["night"].isoformat()


def test_ecosystem_unique_wrong_id(client: TestClient):
    response = client.get("/api/gaia/ecosystem/u/wrong_id")
    assert response.status_code == 404


def test_ecosystem_update_request_failure_user(client_user: TestClient):
    response = client_user.put(f"/api/gaia/ecosystem/u/{ecosystem_uid}")
    assert response.status_code == 403


def test_ecosystem_update_request_failure_payload(client_operator: TestClient):
    response = client_operator.put(f"/api/gaia/ecosystem/u/{ecosystem_uid}")
    assert response.status_code == 422


def test_ecosystem_update_request_success(client_operator: TestClient):
    payload = {
        "name": "UpdatedEcosystem",
    }
    response = client_operator.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}",
        json=payload,
    )
    assert response.status_code == 202


def test_ecosystem_delete_request_failure_anon(client: TestClient):
    response = client.delete(f"/api/gaia/ecosystem/u/{ecosystem_uid}")
    assert response.status_code == 403


def test_ecosystem_delete_request_success(client_operator: TestClient):
    response = client_operator.delete(f"/api/gaia/ecosystem/u/{ecosystem_uid}")
    assert response.status_code == 202


# ------------------------------------------------------------------------------
#   Ecosystem management
# ------------------------------------------------------------------------------
def test_managements_available(client: TestClient):
    response = client.get("/api/gaia/ecosystem/managements_available")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert len(data) == len([m for m in ManagementFlags])


def test_managements(client: TestClient):
    response = client.get("/api/gaia/ecosystem/management")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    for management, value in management_data.items():
        if data.get(management):
            # TODO: better handle new managements
            assert data[0][management] == value


def test_management_unique(client: TestClient):
    response = client.get(f"/api/gaia/ecosystem/u/{ecosystem_uid}/management")
    assert response.status_code == 200

    data = json.loads(response.text)
    for management, value in management_data.items():
        if data.get(management):
            # TODO: better handle new managements
            assert data[0][management] == value


def test_update_management_request_failure_user(client_user: TestClient):
    response = client_user.put(f"/api/gaia/ecosystem/u/{ecosystem_uid}/management")
    assert response.status_code == 403


def test_update_management_request_failure_payload(client_operator: TestClient):
    response = client_operator.put(f"/api/gaia/ecosystem/u/{ecosystem_uid}/management")
    assert response.status_code == 422


def test_update_management_request_success(client_operator: TestClient):
    payload = management_data.copy()
    payload.update({
        "sensors": False,
        "pictures": True,
    })

    response = client_operator.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/management",
        json=payload,
    )
    assert response.status_code == 202


# ------------------------------------------------------------------------------
#   Ecosystem sensors skeleton
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ecosystems_sensors_skeleton(
        client: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client.get("/api/gaia/ecosystem/sensors_skeleton")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    async with db.scoped_session() as session:
        time_window = create_time_window()
        ecosystem = await Ecosystem.get(session, ecosystem_uid)
        skeleton = await ecosystem.sensors_data_skeleton(session, time_window)
        assert data == skeleton


@pytest.mark.asyncio
async def test_ecosystem_sensors_skeleton_unique(
        client: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client.get(f"/api/gaia/ecosystem/u/{ecosystem_uid}/sensors_skeleton")
    assert response.status_code == 200

    data = json.loads(response.text)
    async with db.scoped_session() as session:
        time_window = create_time_window()
        ecosystem = await Ecosystem.get(session, ecosystem_uid)
        skeleton = await ecosystem.sensors_data_skeleton(session, time_window)
        assert data == skeleton


# ------------------------------------------------------------------------------
#   Ecosystem light
# ------------------------------------------------------------------------------
def test_light(client: TestClient):
    response = client.get("/api/gaia/ecosystem/light")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    assert data["method"] == light_data["method"].value
    assert time.fromisoformat(data["morning_start"]) == light_data["morning_start"]
    assert time.fromisoformat(data["morning_end"]) == light_data["morning_end"]
    assert time.fromisoformat(data["evening_start"]) == light_data["evening_start"]
    assert time.fromisoformat(data["evening_end"]) == light_data["evening_end"]


def test_light_unique(client: TestClient):
    response = client.get(f"/api/gaia/ecosystem/u/{ecosystem_uid}/light")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["method"] == light_data["method"].value
    assert time.fromisoformat(data["morning_start"]) == light_data["morning_start"]
    assert time.fromisoformat(data["morning_end"]) == light_data["morning_end"]
    assert time.fromisoformat(data["evening_start"]) == light_data["evening_start"]
    assert time.fromisoformat(data["evening_end"]) == light_data["evening_end"]


def test_update_light_request_failure_user(client_user: TestClient):
    response = client_user.put(f"/api/gaia/ecosystem/u/{ecosystem_uid}/light")
    assert response.status_code == 403


def test_update_light_request_failure_payload(client_operator: TestClient):
    response = client_operator.put(f"/api/gaia/ecosystem/u/{ecosystem_uid}/light")
    assert response.status_code == 422


def test_update_light_request_success(client_operator: TestClient):
    payload = {"method": "mimic"}

    response = client_operator.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/light",
        json=payload,
    )
    assert response.status_code == 202


# ------------------------------------------------------------------------------
#   Ecosystem environment parameters
# ------------------------------------------------------------------------------
def test_environment_parameters(client: TestClient):
    response = client.get("/api/gaia/ecosystem/environment_parameters")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    assert data["parameter"] == climate["parameter"]
    assert data["day"] == climate["day"]
    assert data["night"] == climate["night"]
    assert data["hysteresis"] == climate["hysteresis"]


def test_environment_parameters_unique(client: TestClient):
    response = client.get(f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    assert data["parameter"] == climate["parameter"]
    assert data["day"] == climate["day"]
    assert data["night"] == climate["night"]
    assert data["hysteresis"] == climate["hysteresis"]


def test_create_environment_parameter_request_failure_user(client_user: TestClient):
    response = client_user.post(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters")
    assert response.status_code == 403


def test_create_environment_parameter_request_failure_payload(client_operator: TestClient):
    response = client_operator.post(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters")
    assert response.status_code == 422


def test_create_environment_parameter_request_success(client_operator: TestClient):
    payload = climate.copy()
    payload["parameter"] = "humidity"

    response = client_operator.post(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters",
        json=payload,
    )
    assert response.status_code == 202


def test_update_environment_parameter_request_failure_user(client_user: TestClient):
    response = client_user.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters/temperature")
    assert response.status_code == 403


def test_update_environment_parameter_request_failure_payload(client_operator: TestClient):
    response = client_operator.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters/temperature")
    assert response.status_code == 422


def test_update_environment_parameter_request_success(client_operator: TestClient):
    payload = climate.copy()
    del payload["parameter"]
    payload["day"] = 37.0

    response = client_operator.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters/temperature",
        json=payload,
    )
    assert response.status_code == 202


def test_delete_environment_parameter_request_failure_anon(client: TestClient):
    response = client.delete(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters/temperature")
    assert response.status_code == 403


def test_delete_environment_parameter_request_success(client_operator: TestClient):
    response = client_operator.delete(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/environment_parameters/temperature")
    assert response.status_code == 202


# ------------------------------------------------------------------------------
#   Ecosystem hardware
# ------------------------------------------------------------------------------
def test_get_ecosystem_hardware(client: TestClient):
    response = client.get(f"/api/gaia/ecosystem/u/{ecosystem_uid}/hardware")
    assert response.status_code == 200

    data = json.loads(response.text)
    hardware = data[0]
    assert hardware["uid"] == hardware_data["uid"]
    assert hardware["level"] == hardware_data["level"]
    assert hardware["last_log"] is None
    assert hardware["measures"][0]["name"] == hardware_data["measures"][0]


def test_create_ecosystem_hardware_request_failure_user(client_user: TestClient):
    response = client_user.post(f"/api/gaia/ecosystem/u/{ecosystem_uid}/hardware")
    assert response.status_code == 403


def test_create_ecosystem_hardware_request_failure_payload(client_operator: TestClient):
    response = client_operator.post(f"/api/gaia/ecosystem/u/{ecosystem_uid}/hardware")
    assert response.status_code == 422


def test_create_ecosystem_hardware_request_success(client_operator: TestClient):
    payload = hardware_data.copy()
    del payload["uid"]

    response = client_operator.post(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/hardware",
        json=payload,
    )
    assert response.status_code == 202


# ------------------------------------------------------------------------------
#   Ecosystem current data
# ------------------------------------------------------------------------------
def test_current_data(client: TestClient):
    response = client.get("/api/gaia/ecosystem/current_data")
    assert response.status_code == 200

    data = json.loads(response.text)[0]
    assert data["ecosystem_uid"] == ecosystem_uid
    inner_data = data["data"][0]
    assert datetime.fromisoformat(inner_data["timestamp"]) == sensors_data["timestamp"]
    assert inner_data["sensor_uid"] == sensor_record.sensor_uid
    assert inner_data["measure"] == sensor_record.measure
    assert inner_data["value"] == sensor_record.value


def test_current_data_unique(client: TestClient):
    response = client.get(f"/api/gaia/ecosystem/u/{ecosystem_uid}/current_data")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data["ecosystem_uid"] == ecosystem_uid
    inner_data = data["data"][0]
    assert datetime.fromisoformat(inner_data["timestamp"]) == sensors_data["timestamp"]
    assert inner_data["sensor_uid"] == sensor_record.sensor_uid
    assert inner_data["measure"] == sensor_record.measure
    assert inner_data["value"] == sensor_record.value


# ------------------------------------------------------------------------------
#   Ecosystem actuators state
# ------------------------------------------------------------------------------
def test_turn_actuator_failure_user(
        client_user: TestClient,
):
    response = client_user.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/turn_actuator"
    )
    assert response.status_code == 403


def test_turn_actuator_failure_payload(client_operator: TestClient):
    response = client_operator.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/turn_actuator",
    )
    assert response.status_code == 422


def test_turn_actuator_success(client_operator: TestClient):
    payload = {
        "actuator": "heater",
        "mode": "automatic",
        "countdown": 0.0,
    }
    response = client_operator.put(
        f"/api/gaia/ecosystem/u/{ecosystem_uid}/turn_actuator",
        json=payload
    )
    assert response.status_code == 202
