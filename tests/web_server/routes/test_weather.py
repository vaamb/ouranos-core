from fastapi.testclient import TestClient


def test_sun_times(client: TestClient):
    response = client.get("/api/weather/sun_times")
    assert response.status_code == 204


def test_forecast(client: TestClient):
    response = client.get("/api/weather/forecast")
    assert response.status_code == 204


def test_forecast_currently(client: TestClient):
    response = client.get("/api/weather/forecast/currently")
    assert response.status_code == 204


def test_forecast_hourly(client: TestClient):
    response = client.get("/api/weather/forecast/hourly")
    assert response.status_code == 204


def test_forecast_daily(client: TestClient):
    response = client.get("/api/weather/forecast/daily")
    assert response.status_code == 204
