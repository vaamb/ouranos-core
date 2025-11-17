from datetime import datetime, time

from fastapi.testclient import TestClient
import pytest

import gaia_validators as gv

from ouranos import json
from ouranos.core.database.models.gaia import Ecosystem, Engine

import tests.data.gaia as g_data
from tests.utils import MockAsyncDispatcher
from tests.class_fixtures import (
    ActuatorsAware, EcosystemAware, ClimateAware, UsersAware)


# ------------------------------------------------------------------------------
#   Base ecosystem info
# ------------------------------------------------------------------------------
class TestEcosystemCore(EcosystemAware, UsersAware):
    @pytest.mark.asyncio
    async def test_engine_relationship(self, client: TestClient, db):
        async with db.scoped_session() as session:
            engines = await Engine.get_multiple_by_id(session, engines_id=None)
            ecosystems = await Ecosystem.get_multiple_by_id(
                session, ecosystems_id=None)
            assert len(engines) == 1
            assert len(ecosystems) == 1
            assert len(engines[0].ecosystems) == 1
            assert ecosystems[0].engine.uid == engines[0].uid
            assert engines[0].ecosystems[0].uid == ecosystems[0].uid

    def test_get_ecosystems(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem")
        assert response.status_code == 200

        data = json.loads(response.text)[0]
        assert data["uid"] == g_data.ecosystem_uid
        assert data["name"] == g_data.ecosystem_name
        assert data["engine_uid"] == g_data.engine_uid
        assert data["status"] == g_data.ecosystem_dict["status"]
        assert datetime.fromisoformat(data["registration_date"]) == \
               g_data.ecosystem_dict["registration_date"]

    def test_create_ecosystem_failure_user(self, client_user: TestClient):
        response = client_user.post("/api/gaia/ecosystem/u")
        assert response.status_code == 403

    def test_create_ecosystem_failure_payload(self, client_operator: TestClient):
        response = client_operator.post("/api/gaia/ecosystem/u")
        assert response.status_code == 422

    def test_create_ecosystem_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = {
            "name": "NewEcosystem",
            "engine_uid": g_data.engine_uid,
        }
        response = client_operator.post(
            "/api/gaia/ecosystem/u",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] is None
        assert dispatched["data"]["action"] == gv.CrudAction.create
        assert dispatched["data"]["target"] == "ecosystem"
        assert dispatched["data"]["data"]["name"] == payload["name"]

    def test_get_ecosystem(self, client: TestClient):
        response = client.get(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["uid"] == g_data.ecosystem_uid
        assert data["name"] == g_data.ecosystem_name
        assert data["engine_uid"] == g_data.engine_uid
        assert data["status"] == g_data.ecosystem_dict["status"]
        assert datetime.fromisoformat(data["registration_date"]) == \
               g_data.ecosystem_dict["registration_date"]

    def test_get_ecosystem_failure_wrong_id(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/u/wrong_id")
        assert response.status_code == 404

    def test_update_ecosystem_failure_user(self, client_user: TestClient):
        response = client_user.put(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}")
        assert response.status_code == 403

    def test_update_ecosystem_failure_payload(self, client_operator: TestClient):
        response = client_operator.put(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}")
        assert response.status_code == 422

    def test_update_ecosystem_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = {
            "name": "UpdatedEcosystem",
        }
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.update
        assert dispatched["data"]["target"] == "ecosystem"
        assert dispatched["data"]["data"]["name"] == payload["name"]

    def test_delete_ecosystem_failure_user(self, client: TestClient):
        response = client.delete(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}")
        assert response.status_code == 403

    def test_delete_ecosystem_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        response = client_operator.delete(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}")
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.delete
        assert dispatched["data"]["target"] == "ecosystem"
        assert dispatched["data"]["data"] == g_data.ecosystem_uid


# ------------------------------------------------------------------------------
#   Ecosystem management
# ------------------------------------------------------------------------------
class TestEcosystemManagement(EcosystemAware, UsersAware):
    def test_get_managements_available(self,client: TestClient):
        response = client.get("/api/gaia/ecosystem/managements_available")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == len([m for m in gv.ManagementFlags])

    def test_get_managements(self,client: TestClient):
        response = client.get("/api/gaia/ecosystem/management")
        assert response.status_code == 200

        data = json.loads(response.text)[0]
        for management, value in g_data.management_data.items():
            if data.get(management):
                assert data[0][management] == value
        assert not data["ecosystem_data"]
        assert not data["environment_data"]
        assert not data["plants_data"]

    def test_get_management(self,client: TestClient):
        response = client.get(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/management")
        assert response.status_code == 200

        data = json.loads(response.text)
        for management, value in g_data.management_data.items():
            if data.get(management):
                assert data[0][management] == value
        assert not data["ecosystem_data"]
        assert not data["environment_data"]
        assert not data["plants_data"]

    def test_update_management_failure_user(self,client_user: TestClient):
        response = client_user.put(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/management")
        assert response.status_code == 403

    def test_update_management_failure_payload(self,client_operator: TestClient):
        response = client_operator.put(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/management")
        assert response.status_code == 422

    def test_update_management_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = g_data.management_data.copy()
        payload.update({
            "sensors": False,
            "pictures": True,
        })

        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/management",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.update
        assert dispatched["data"]["target"] == "management"
        assert dispatched["data"]["data"]["pictures"] == payload["pictures"]


# ------------------------------------------------------------------------------
#   Ecosystem light
# ------------------------------------------------------------------------------
class TestEcosystemLight(ClimateAware, UsersAware):
    def test_get_ecosystems_lighting(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/light")
        assert response.status_code == 200

        data = json.loads(response.text)[0]

        assert data["span"] == g_data.sky["span"].name
        assert data["lighting"] == g_data.sky["lighting"].name
        assert data["target"] is None
        assert time.fromisoformat(data["day"]) == g_data.sky["day"]
        assert time.fromisoformat(data["night"]) == g_data.sky["night"]
        assert time.fromisoformat(data["morning_start"]) == g_data.light_data["morning_start"]
        assert time.fromisoformat(data["morning_end"]) == g_data.light_data["morning_end"]
        assert time.fromisoformat(data["evening_start"]) == g_data.light_data["evening_start"]
        assert time.fromisoformat(data["evening_end"]) == g_data.light_data["evening_end"]

    def test_get_ecosystem_lighting(self, client: TestClient):
        response = client.get(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/light")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["span"] == g_data.sky["span"].name
        assert data["lighting"] == g_data.sky["lighting"].name
        assert data["target"] is None
        assert time.fromisoformat(data["day"]) == g_data.sky["day"]
        assert time.fromisoformat(data["night"]) == g_data.sky["night"]
        assert time.fromisoformat(data["morning_start"]) == g_data.light_data["morning_start"]
        assert time.fromisoformat(data["morning_end"]) == g_data.light_data["morning_end"]
        assert time.fromisoformat(data["evening_start"]) == g_data.light_data["evening_start"]
        assert time.fromisoformat(data["evening_end"]) == g_data.light_data["evening_end"]

    def test_update_ecosystem_lighting_failure_user(self, client_user: TestClient):
        response = client_user.put(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/light")
        assert response.status_code == 403

    def test_update_ecosystem_lighting_failure_payload(self, client_operator: TestClient):
        response = client_operator.put(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/light")
        assert response.status_code == 422

    def test_update_ecosystem_lighting_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = {"lighting": "elongate"}

        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/light",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.update
        assert dispatched["data"]["target"] == "nycthemeral_config"
        assert dispatched["data"]["data"]["lighting"] == gv.LightingMethod[payload["lighting"]]


# ------------------------------------------------------------------------------
#   Ecosystem environment parameters
# ------------------------------------------------------------------------------
class TestEcosystemEnvironmentParameters(ClimateAware, UsersAware):
    def test_get_ecosystems_environment_parameters(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/environment_parameter")
        assert response.status_code == 200

        data = json.loads(response.text)[0]
        assert data["uid"] == g_data.ecosystem_uid
        parameter_1 = data["environment_parameters"][0]
        assert parameter_1["parameter"] == g_data.climate["parameter"]
        assert parameter_1["day"] == g_data.climate["day"]
        assert parameter_1["night"] == g_data.climate["night"]
        assert parameter_1["hysteresis"] == g_data.climate["hysteresis"]

    def test_get_ecosystem_environment_parameters(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["uid"] == g_data.ecosystem_uid
        parameter_1 = data["environment_parameters"][0]
        assert parameter_1["day"] == g_data.climate["day"]
        assert parameter_1["night"] == g_data.climate["night"]
        assert parameter_1["hysteresis"] == g_data.climate["hysteresis"]
        assert parameter_1["alarm"] == g_data.climate["alarm"]
        assert parameter_1["linked_actuator_group_increase"] == \
               g_data.climate["linked_actuators"]["increase"]
        assert parameter_1["linked_actuator_group_decrease"] == \
               g_data.climate["linked_actuators"]["decrease"]
        assert parameter_1["linked_measure"] == g_data.climate["linked_measure"]

    def test_create_environment_parameter_failure_user(self, client_user: TestClient):
        response = client_user.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/u")
        assert response.status_code == 403

    def test_create_environment_parameter_failure_payload(self, client_operator: TestClient):
        response = client_operator.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/u")
        assert response.status_code == 422

    def test_create_environment_parameter_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = g_data.climate.copy()
        payload["parameter"] = "humidity"

        response = client_operator.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/u",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.create
        assert dispatched["data"]["target"] == "environment_parameter"
        assert dispatched["data"]["data"]["parameter"] == gv.ClimateParameter[payload["parameter"]]
        assert dispatched["data"]["data"]["day"] == payload["day"]

    def test_get_ecosystem_environment_parameter(self, client: TestClient):
        parameter = g_data.climate["parameter"]
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/"
            f"u/{parameter}"
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["parameter"] == g_data.climate["parameter"]
        assert data["day"] == g_data.climate["day"]
        assert data["night"] == g_data.climate["night"]
        assert data["hysteresis"] == g_data.climate["hysteresis"]

    def test_update_ecosystem_environment_parameter_failure_user(self, client_user: TestClient):
        response = client_user.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/u/temperature")
        assert response.status_code == 403

    def test_update_ecosystem_environment_parameter_failure_payload(self, client_operator: TestClient):
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/u/temperature")
        assert response.status_code == 422

    def test_update_ecosystem_environment_parameter_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        parameter = "temperature"
        payload = g_data.climate.copy()
        del payload["parameter"]
        payload["day"] = 37.0

        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/"
            f"u/{parameter}",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.update
        assert dispatched["data"]["target"] == "environment_parameter"
        assert dispatched["data"]["data"]["parameter"] == gv.ClimateParameter[parameter]
        assert dispatched["data"]["data"]["day"] == payload["day"]

    def test_delete_ecosystem_environment_parameter_failure_user(self, client: TestClient):
        response = client.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/u/temperature")
        assert response.status_code == 403

    def test_delete_ecosystem_environment_parameter_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        parameter = "temperature"
        response = client_operator.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/environment_parameter/u/{parameter}")
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.delete
        assert dispatched["data"]["target"] == "environment_parameter"
        assert dispatched["data"]["data"] == parameter


# ------------------------------------------------------------------------------
#   Weather events
# ------------------------------------------------------------------------------
class TestEcosystemWeatherEvents(ClimateAware, UsersAware):
    def test_get_ecosystems_weather_events(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/weather_event")
        assert response.status_code == 200

        data = json.loads(response.text)[0]
        assert data["uid"] == g_data.ecosystem_uid
        event_1 = data["weather_events"][0]
        assert event_1["parameter"] == g_data.weather["parameter"]
        assert event_1["pattern"] == g_data.weather["pattern"]
        assert event_1["duration"] == g_data.weather["duration"]
        assert event_1["level"] == g_data.weather["level"]
        assert event_1["linked_actuator"] == g_data.weather["linked_actuator"]

    def test_get_ecosystem_weather_events(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["uid"] == g_data.ecosystem_uid
        event_1 = data["weather_events"][0]
        assert event_1["parameter"] == g_data.weather["parameter"]
        assert event_1["pattern"] == g_data.weather["pattern"]
        assert event_1["duration"] == g_data.weather["duration"]
        assert event_1["level"] == g_data.weather["level"]
        assert event_1["linked_actuator"] == g_data.weather["linked_actuator"]

    def test_create_ecosystem_weather_event_failure_user(self, client_user: TestClient):
        response = client_user.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u")
        assert response.status_code == 403

    def test_create_ecosystem_weather_event_failure_payload(self, client_operator: TestClient):
        response = client_operator.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u")
        assert response.status_code == 422

    def test_create_ecosystem_weather_event_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        payload = g_data.weather.copy()
        payload["parameter"] = gv.WeatherParameter.rain

        response = client_operator.post(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.create
        assert dispatched["data"]["target"] == "weather_event"
        assert dispatched["data"]["data"]["parameter"] == payload["parameter"]
        assert dispatched["data"]["data"]["pattern"] == payload["pattern"]
        assert dispatched["data"]["data"]["duration"] == payload["duration"]
        assert dispatched["data"]["data"]["level"] == payload["level"]
        assert dispatched["data"]["data"]["linked_actuator"] == payload["linked_actuator"]

    def test_get_ecosystem_weather_event(self, client: TestClient):
        parameter = g_data.weather["parameter"]
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u/{parameter}"
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["parameter"] == g_data.weather["parameter"]
        assert data["pattern"] == g_data.weather["pattern"]
        assert data["duration"] == g_data.weather["duration"]
        assert data["level"] == g_data.weather["level"]
        assert data["linked_actuator"] == g_data.weather["linked_actuator"]

    def test_update_ecosystem_weather_event_failure_user(self, client_user: TestClient):
        response = client_user.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u/rain")
        assert response.status_code == 403

    def test_update_ecosystem_weather_event_failure_payload(self, client_operator: TestClient):
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u/rain")
        assert response.status_code == 422

    def test_update_ecosystem_weather_event_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        parameter = "rain"
        payload = g_data.weather.copy()
        del payload["parameter"]
        payload["duration"] = 42.0

        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u/{parameter}",
            json=payload,
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.update
        assert dispatched["data"]["target"] == "weather_event"
        assert dispatched["data"]["data"]["parameter"] == parameter
        assert dispatched["data"]["data"]["pattern"] == payload["pattern"]
        assert dispatched["data"]["data"]["duration"] == payload["duration"]
        assert dispatched["data"]["data"]["level"] == payload["level"]
        assert dispatched["data"]["data"]["linked_actuator"] == payload["linked_actuator"]

    def test_delete_ecosystem_weather_event_failure_user(self, client: TestClient):
        response = client.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u/temperature")
        assert response.status_code == 403

    def test_delete_ecosystem_weather_event_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        parameter = g_data.weather["parameter"]
        response = client_operator.delete(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/weather_event/u/{parameter}")
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "crud"
        assert dispatched["data"]["routing"]["engine_uid"] == g_data.engine_uid
        assert dispatched["data"]["routing"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["action"] == gv.CrudAction.delete
        assert dispatched["data"]["target"] == "weather_event"
        assert dispatched["data"]["data"] == parameter


# ------------------------------------------------------------------------------
#   Ecosystem actuators state
# ------------------------------------------------------------------------------
class TestEcosystemActuators(ActuatorsAware, UsersAware):
    def test_get_ecosystem_actuator_records(self, client: TestClient):
        actuator = g_data.actuator_record.type.name
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/actuator_records/u/{actuator}")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["uid"] == g_data.ecosystem_uid
        assert data["actuator_type"] == actuator
        inner_data = data["values"][0]
        assert datetime.fromisoformat(inner_data[0]) == g_data.actuator_record.timestamp
        assert inner_data[1] == g_data.actuator_record.active
        assert inner_data[2] == g_data.actuator_record.mode
        assert inner_data[3] == g_data.actuator_record.status
        assert inner_data[4] == g_data.actuator_record.level

    def test_turn_actuator_failure_user(self, client_user: TestClient):
        response = client_user.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/turn_actuator/u/heater"
        )
        assert response.status_code == 403

    def test_turn_actuator_failure_payload(self, client_operator: TestClient):
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/turn_actuator/u/heater",
        )
        assert response.status_code == 422

    def test_turn_actuator_success(
            self,
            client_operator: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        actuator = "heater"
        payload = {
            "mode": "automatic",
            "countdown": 0.0,
        }
        response = client_operator.put(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/turn_actuator/u/{actuator}",
            json=payload
        )
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "turn_actuator"
        assert dispatched["data"]["ecosystem_uid"] == g_data.ecosystem_uid
        assert dispatched["data"]["actuator"] == actuator
        assert dispatched["data"]["mode"] == payload["mode"]
        assert dispatched["data"]["countdown"] == payload["countdown"]
