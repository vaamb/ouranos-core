from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.app import CalendarEvent

from tests.data.app import calendar_event

title = "Just a test ..."
start = datetime.now(tz=timezone.utc)
creation_payload = {
    "level": 0,
    "title": title,
    "description": "... and its description",
    "start_time": (start + timedelta(days=7)).isoformat(),
    "end_time": (start + timedelta(days=14)).isoformat(),
}


def test_calendar_failure_unauthorized(client: TestClient):
    response = client.get("/api/app/services/calendar")
    assert response.status_code == 403


def test_calendar_success(client_user: TestClient):
    response = client_user.get("/api/app/services/calendar")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data[0]["level"] == calendar_event["level"].value
    assert data[0]["title"] == calendar_event["title"]
    assert data[0]["description"] == calendar_event["description"]


def test_event_creation_failure_unauthorized(client: TestClient):
    response = client.post(
        "/api/app/services/calendar/u",
        json=creation_payload,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_event_creation_success(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client_operator.post(
        "/api/app/services/calendar/u",
        json=creation_payload,
    )
    assert response.status_code == 202

    async with db.scoped_session() as session:
        events = await CalendarEvent.get_multiple(session)
        failed = True
        for event in events:
            if event.title == title:
                failed = False
                break
        assert not failed


def test_event_update_failure_unauthorized(client: TestClient):
    response = client.put("/api/app/services/calendar/u/1")
    assert response.status_code == 403


def test_event_update_failure_wrong_user(client_operator: TestClient):
    description = "Change the description"
    payload = {
        "description": description,
    }
    response = client_operator.put(
        "/api/app/services/calendar/u/1",
        json=payload,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_event_update_success(
        client_user: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    description = "Change the description"
    payload = {
        "description": description,
    }
    response = client_user.put(
        "/api/app/services/calendar/u/1",
        json=payload,
    )
    assert response.status_code == 202

    async with db.scoped_session() as session:
        events = await CalendarEvent.get_multiple(session)
        failed = True
        for event in events:
            if event.description == description:
                failed = False
                break
        assert not failed
