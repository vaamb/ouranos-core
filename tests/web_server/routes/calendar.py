from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import CalendarEvent

from tests.data.app import calendar_event_public, calendar_event_users
from tests.class_fixtures import EventsAware, ServicesEnabled, UsersAware


title = "Just a test ..."
start = datetime.now(tz=timezone.utc)
creation_payload = {
    "level": 0,
    "visibility": 0,
    "title": title,
    "description": "... and its description",
    "start_time": (start + timedelta(days=7)).isoformat(),
    "end_time": (start + timedelta(days=14)).isoformat(),
}


class TestCalendar(EventsAware, ServicesEnabled, UsersAware):
    def test_get_public(self, client: TestClient):
        response = client.get("/api/app/services/calendar")
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 1
        assert data[0]["level"] == calendar_event_public["level"].value
        assert data[0]["title"] == calendar_event_public["title"]

    def test_get_filter_visibility_user(self, client_user: TestClient):
        response = client_user.get(
            "/api/app/services/calendar",
            params={"visibility": "users"},
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        assert len(data) == 2
        # Public event starts before
        assert data[0]["level"] == calendar_event_public["level"].value
        assert data[0]["title"] == calendar_event_public["title"]
        # User event starts later and so is second
        assert data[1]["level"] == calendar_event_users["level"].value
        assert data[1]["title"] == calendar_event_users["title"]
        assert data[1]["description"] == calendar_event_users["description"]

    def test_get_filter_visibility_admin(self, client_admin: TestClient):
        # Admins go through the unrestricted `get_multiple` branch and can see
        # every event regardless of visibility
        response = client_admin.get(
            "/api/app/services/calendar",
            params={"visibility": "private"},
        )
        assert response.status_code == 200

        data = json.loads(response.text)
        titles = {event["title"] for event in data}
        assert calendar_event_public["title"] in titles
        assert calendar_event_users["title"] in titles


@pytest.mark.asyncio
class TestEventCreation(EventsAware, ServicesEnabled, UsersAware):
    def test_create_failure_anon(self, client: TestClient):
        response = client.post(
            "/api/app/services/calendar/u",
            json=creation_payload,
        )
        assert response.status_code == 403

    async def test_create_success(
            self,
            client_operator: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client_operator.post(
            "/api/app/services/calendar/u",
            json=creation_payload,
        )
        assert response.status_code == 202

        async with db.scoped_session() as session:
            events = await CalendarEvent.get_multiple_with_visibility(session)
        assert any(event.title == title for event in events)


@pytest.mark.asyncio
class TestEventUpdate(EventsAware, ServicesEnabled, UsersAware):
    def test_update_failure_anon(self, client: TestClient):
        response = client.put("/api/app/services/calendar/u/1")
        assert response.status_code == 403

    def test_update_failure_different_user(self, client_operator: TestClient):
        response = client_operator.put(
            "/api/app/services/calendar/u/1",
            json={"description": "Change the description"},
        )
        assert response.status_code == 403

    def test_update_failure_not_found(self, client_user: TestClient):
        response = client_user.put(
            "/api/app/services/calendar/u/404",
            json={"description": "Change the description"},
        )
        assert response.status_code == 404

    async def test_update_success(
            self,
            client_user: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        description = "Change the description"
        response = client_user.put(
            "/api/app/services/calendar/u/1",
            json={"description": description},
        )
        assert response.status_code == 202

        async with db.scoped_session() as session:
            event = await CalendarEvent.get(session, event_id=1)
        assert event.description == description


@pytest.mark.asyncio
class TestEventDeletion(EventsAware, ServicesEnabled, UsersAware):
    def test_delete_failure_anon(self, client: TestClient):
        response = client.delete("/api/app/services/calendar/u/1")
        assert response.status_code == 403

    def test_delete_failure_different_user(self, client_operator: TestClient):
        response = client_operator.delete("/api/app/services/calendar/u/1")
        assert response.status_code == 403

    def test_delete_failure_not_found(self, client_user: TestClient):
        response = client_user.delete("/api/app/services/calendar/u/404")
        assert response.status_code == 404

    async def test_delete_success(
            self,
            client_user: TestClient,
            db: AsyncSQLAlchemyWrapper,
    ):
        response = client_user.delete("/api/app/services/calendar/u/1")
        assert response.status_code == 202

        # The event is inactivated rather than removed
        async with db.scoped_session() as session:
            event = await CalendarEvent.get(session, event_id=1)
        assert event.active is False
