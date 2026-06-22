from datetime import datetime, timedelta

from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import Ecosystem
from ouranos.core.utils import create_time_window

import tests.data.gaia as g_data
from tests.class_fixtures import HardwareAware, SensorsAware


class TestMeasuresAvailable(HardwareAware):
    def test_get(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/sensor/measures_available")
        assert response.status_code == 200

        # Measures are derived from the registered hardware
        data = json.loads(response.text)
        assert {"name": "temperature", "unit": "°C"} in data


@pytest.mark.asyncio
class TestSensorsSkeleton(HardwareAware):
    async def test_get(
            self,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client.get("/api/gaia/ecosystem/sensor/skeleton")
        assert response.status_code == 200

        data = json.loads(response.text)[0]
        async with db.scoped_session() as session:
            time_window = create_time_window()
            ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
            skeleton = await ecosystem.get_sensors_data_skeleton(
                session, time_window=time_window)
        assert data["uid"] == skeleton["uid"] == g_data.ecosystem_uid
        assert data["name"] == skeleton["name"] == g_data.ecosystem_name
        assert data["sensors_skeleton"] == skeleton["sensors_skeleton"]
        assert datetime.fromisoformat(data["span"][0]) == skeleton["span"][0]
        assert datetime.fromisoformat(data["span"][1]) == skeleton["span"][1]

    async def test_get_unique(
            self,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client.get(f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/sensor/skeleton")
        assert response.status_code == 200

        data = json.loads(response.text)
        async with db.scoped_session() as session:
            time_window = create_time_window()
            ecosystem = await Ecosystem.get(session, uid=g_data.ecosystem_uid)
            skeleton = await ecosystem.get_sensors_data_skeleton(
                session, time_window=time_window)
        assert data["uid"] == skeleton["uid"] == g_data.ecosystem_uid
        assert data["name"] == skeleton["name"] == g_data.ecosystem_name
        assert data["sensors_skeleton"] == skeleton["sensors_skeleton"]
        assert datetime.fromisoformat(data["span"][0]) == skeleton["span"][0]
        assert datetime.fromisoformat(data["span"][1]) == skeleton["span"][1]

    async def test_get_unique_failure_wrong_ecosystem(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/u/wrong_uid/sensor/skeleton")
        assert response.status_code == 404


class TestSensorsCurrentData(SensorsAware):
    def test_get(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/sensor/data/current")
        assert response.status_code == 200

        data = json.loads(response.text)[0]
        assert data["uid"] == g_data.ecosystem_uid
        inner_data = data["values"][0]
        assert datetime.fromisoformat(inner_data["timestamp"]) == g_data.sensors_data["timestamp"]
        assert inner_data["sensor_uid"] == g_data.sensor_record.sensor_uid
        assert inner_data["measure"] == g_data.sensor_record.measure
        assert inner_data["value"] == g_data.sensor_record.value

    def test_get_unique(self, client: TestClient):
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

    def test_get_unique_failure_wrong_ecosystem(self, client: TestClient):
        response = client.get("/api/gaia/ecosystem/u/wrong_uid/sensor/data/current")
        assert response.status_code == 404


class TestSensorData(SensorsAware):
    # The only sensor added by the fixture is a thermometer (measure: temperature)
    def test_get_current(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}"
            f"/sensor/u/{g_data.hardware_uid}/data/{g_data.sensor_record.measure}"
            f"/current")
        assert response.status_code == 200

        current_data = json.loads(response.text)
        # Most data is the same as the one given by hardware, focus on the difference
        assert current_data["measure"] == g_data.sensor_record.measure
        current_value = current_data["values"][0]
        assert datetime.fromisoformat(current_value[0]) == g_data.sensors_data["timestamp"]
        assert current_value[1] == g_data.sensor_record.value

    def test_get_current_failure_wrong_ecosystem(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/wrong_uid/sensor/u/{g_data.hardware_uid}"
            f"/data/{g_data.sensor_record.measure}/current")
        assert response.status_code == 404

    def test_get_current_failure_wrong_sensor(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/sensor/u/wrong_uid"
            f"/data/{g_data.sensor_record.measure}/current")
        assert response.status_code == 404

    def test_get_current_failure_camera_unsupported(self, client: TestClient):
        # Cameras are sensors but expose no current measure
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}"
            f"/sensor/u/{g_data.camera_config['uid']}"
            f"/data/{g_data.sensor_record.measure}/current")
        assert response.status_code == 404

    def test_get_current_failure_unavailable_measure(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}"
            f"/sensor/u/{g_data.hardware_uid}/data/humidity/current")
        assert response.status_code == 400

    def test_get_historic(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}"
            f"/sensor/u/{g_data.hardware_uid}/data/{g_data.sensor_record.measure}"
            f"/historic")
        assert response.status_code == 200

        historic_data = json.loads(response.text)
        # Most data is the same as the one given by hardware, focus on the difference
        assert historic_data["measure"] == g_data.sensor_record.measure
        historic_value = historic_data["values"][0]
        assert datetime.fromisoformat(historic_value[0]) == \
               (g_data.sensors_data["timestamp"] - timedelta(hours=1))
        assert historic_value[1] == g_data.sensor_record.value

    def test_get_historic_failure_wrong_sensor(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}/sensor/u/wrong_uid"
            f"/data/{g_data.sensor_record.measure}/historic")
        assert response.status_code == 404

    def test_get_historic_failure_unavailable_measure(self, client: TestClient):
        response = client.get(
            f"/api/gaia/ecosystem/u/{g_data.ecosystem_uid}"
            f"/sensor/u/{g_data.hardware_uid}/data/humidity/historic")
        assert response.status_code == 400
