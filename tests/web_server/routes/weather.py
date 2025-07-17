from fastapi.testclient import TestClient


class TestWeather:
    def test_sun_times(self, client: TestClient):
        response = client.get("/api/app/services/weather/sun_times")
        assert response.status_code == 204

    def test_forecast_currently(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/currently")
        assert response.status_code == 204

    def test_forecast_hourly(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/hourly")
        assert response.status_code == 204

    def test_forecast_daily(self, client: TestClient):
        response = client.get("/api/app/services/weather/forecast/daily")
        assert response.status_code == 204
