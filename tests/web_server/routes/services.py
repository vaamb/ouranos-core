from fastapi.testclient import TestClient


class TestServicesRouteProtection:
    def test_route_protection(self, client: TestClient, db):
        response = client.put("/api/app/services/u/weather", json={"status": True})
        assert response.status_code == 202

        response = client.get("/api/app/services/weather/sun_times")
        assert response.status_code in (200, 204)

        response = client.put("/api/app/services/u/weather", json={"status": False})
        assert response.status_code == 202

        response = client.get("/api/app/services/weather/sun_times")
        assert response.status_code == 423
