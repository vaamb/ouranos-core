from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import Service, ServiceLevel, ServiceName

from tests.utils import MockAsyncDispatcher


# All the services are seeded by `insert_services` (with `status=False`), and
# the email service is enabled by `update_email_service_status` as the test
# config provides the required mail variables.
app_services = {
    ServiceName.weather.value,
    ServiceName.calendar.value,
    ServiceName.wiki.value,
    ServiceName.email.value,
}
ecosystem_services = {ServiceName.suntimes.value}


@pytest.mark.asyncio
class TestServices:
    async def test_get(self, client: TestClient, db: AsyncSQLAlchemyWrapper):
        response = client.get("/api/app/services")
        assert response.status_code == 200
        data = json.loads(response.text)

        async with db.scoped_session() as session:
            services = await Service.get_multiple(session)
        assert len(data) == len(services) == len(ServiceName)
        assert {service["name"] for service in data} == \
               {name.value for name in ServiceName}

    def test_get_filter_by_level_app(self, client: TestClient):
        response = client.get("/api/app/services", params={"level": "app"})
        assert response.status_code == 200

        data = json.loads(response.text)
        assert {service["name"] for service in data} == app_services
        assert all(
            service["level"] == ServiceLevel.app.value for service in data)

    def test_get_filter_by_level_ecosystem(self, client: TestClient):
        response = client.get("/api/app/services", params={"level": "ecosystem"})
        assert response.status_code == 200

        data = json.loads(response.text)
        assert {service["name"] for service in data} == ecosystem_services
        assert all(
            service["level"] == ServiceLevel.ecosystem.value for service in data)

    def test_get_filter_by_level_all(self, client: TestClient):
        # 'all' is mapped to `None` and so returns every service
        response = client.get("/api/app/services", params={"level": "all"})
        assert response.status_code == 200

        data = json.loads(response.text)
        assert {service["name"] for service in data} == \
               {name.value for name in ServiceName}

    def test_get_failure_wrong_level(self, client: TestClient):
        response = client.get("/api/app/services", params={"level": "wrong"})
        assert response.status_code == 422


@pytest.mark.asyncio
class TestServiceUpdate:
    def test_update_failure_wrong_name(self, client: TestClient):
        response = client.put(
            "/api/app/services/u/wrong_name", json={"status": True})
        assert response.status_code == 422

    def test_update_failure_payload(self, client: TestClient):
        response = client.put("/api/app/services/u/wiki", json={})
        assert response.status_code == 422

    async def test_update_success(
            self,
            client: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        async with db.scoped_session() as session:
            await Service.update(session, name=ServiceName.wiki, status=False)

        response = client.put("/api/app/services/u/wiki", json={"status": True})
        assert response.status_code == 202

        async with db.scoped_session() as session:
            service = await Service.get(session, name=ServiceName.wiki)
        assert service.status is True

    def test_update_weather_is_dispatched(
            self,
            client: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        response = client.put(
            "/api/app/services/u/weather", json={"status": True})
        assert response.status_code == 202

        dispatched = mock_dispatcher.emit_store[0]
        assert dispatched["event"] == "update_service"
        assert dispatched["namespace"] == "aggregator-internal"
        assert dispatched["data"]["name"] == ServiceName.weather
        assert dispatched["data"]["status"] is True

    def test_update_non_weather_is_not_dispatched(
            self,
            client: TestClient,
            mock_dispatcher: MockAsyncDispatcher,
    ):
        response = client.put("/api/app/services/u/wiki", json={"status": True})
        assert response.status_code == 202
        assert len(mock_dispatcher.emit_store) == 0
