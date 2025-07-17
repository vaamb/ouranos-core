from fastapi.testclient import TestClient

from ouranos import current_app, json
from ouranos.core.database.models.app import services_definition


class TestApp:
    def test_version(self, client: TestClient):
        response = client.get("/api/app/version")
        assert response.status_code == 200
        data = json.loads(response.text)
        assert data == current_app.config["VERSION"]

    def test_logging_config(self, client: TestClient):
        response = client.get("/api/app/logging_period")
        assert response.status_code == 200

    def test_services(self, client: TestClient):
        response = client.get("/api/app/services")
        assert response.status_code == 200
        data = json.loads(response.text)
        assert len(data) == len(services_definition)

    def test_flash_messages(self, client: TestClient):
        response = client.get("/api/app/flash_messages")
        assert response.status_code == 200
        data = json.loads(response.text)
        assert data == []
