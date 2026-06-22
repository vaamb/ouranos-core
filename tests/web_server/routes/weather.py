from datetime import date, timedelta

from fastapi.testclient import TestClient
import pytest_asyncio

import gaia_validators as gv
from gaia_validators.utils import get_sun_times

from ouranos import json
from ouranos.aggregator.sky_watcher import get_weather_test_data
from ouranos.core.caches import CacheFactory

from tests.class_fixtures import ServicesEnabled


coordinates = gv.Coordinates(latitude=42, longitude=0)


class TestWeatherEmpty(ServicesEnabled):
    """The `sky_watcher` cache is empty, so every route returns a 204."""
    def test_get_sun_times(self, client: TestClient):
        response = client.get("/api/app/services/weather/sun_times")
        assert response.status_code == 204

    def test_get_forecast(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast")
        assert response.status_code == 204

    def test_get_forecast_currently(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/currently")
        assert response.status_code == 204

    def test_get_forecast_hourly(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/hourly")
        assert response.status_code == 204

    def test_get_forecast_daily(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/daily")
        assert response.status_code == 204


class TestWeatherFilled(ServicesEnabled):
    """The `sky_watcher` cache is populated, so the routes return their data."""
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_weather_data(self):
        cache = CacheFactory.get("sky_watcher")
        await cache.init()
        await cache.clear()

        weather_data = (await get_weather_test_data(coordinates, "key")).model_dump()
        await cache.set("weather_currently", weather_data["current"])
        await cache.set("weather_hourly", weather_data["hourly"])
        await cache.set("weather_daily", weather_data["daily"])

        days = [date.today() + timedelta(days=i) for i in range(7)]
        sun_times = [get_sun_times(coordinates, day).model_dump() for day in days]
        await cache.set("sun_times", sun_times)

        yield

        # Leave the cache empty so `TestWeather` keeps seeing 204s
        await cache.clear()

    def test_get_sun_times(self, client: TestClient):
        response = client.get("/api/app/services/weather/sun_times")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 7
        assert data[0]["datestamp"] == date.today().isoformat()

    def test_get_forecast(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["currently"]["temperature"] == 25.0
        assert data["currently"]["summary"] == "Cloudy"
        assert data["hourly"][0]["precipitation_probability"] == 20.0
        assert data["daily"][0]["temperature_max"] == 42.0

    def test_get_forecast_exclude_currently(self, client: TestClient):
        response = client.get(
            "/api/app/services/weather/forecast",
            params={"exclude": "currently"},
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["currently"] is None
        assert data["hourly"][0]["precipitation_probability"] == 20.0
        assert data["daily"][0]["temperature_max"] == 42.0

    def test_get_forecast_exclude_all(self, client: TestClient):
        response = client.get(
            "/api/app/services/weather/forecast",
            params={"exclude": ["currently", "hourly", "daily"]},
        )
        assert response.status_code == 204

    def test_get_forecast_currently(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/currently")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert data["temperature"] == 25.0
        assert data["summary"] == "Cloudy"

    def test_get_forecast_hourly(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/hourly")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["precipitation_probability"] == 20.0

    def test_get_forecast_daily(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/daily")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["temperature_min"] == 21.0
        assert data[0]["temperature_max"] == 42.0
