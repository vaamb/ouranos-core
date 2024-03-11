from fastapi.testclient import TestClient
import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos import json
from ouranos.core.database.models.gaia import GaiaWarning

import tests.data.gaia as g_data


def test_warning_failure_anon(client: TestClient):
    response = client.get("/api/gaia/warning")
    assert response.status_code == 403


def test_warning_success(client_user: TestClient):
    response = client_user.get("/api/gaia/warning")
    assert response.status_code == 200

    data = json.loads(response.text)
    assert data[0]["level"] == 0
    assert data[0]["title"] == g_data.gaia_warning["title"]
    assert data[0]["description"] == g_data.gaia_warning["description"]


def test_warning_creation_failure(client_user: TestClient):
    response = client_user.post("/api/gaia/warning/u/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_warning_creation_success(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    title = "Just a test ..."
    payload = {
        "level": 0,
        "title": title,
        "description": "... and its description",
    }
    response = client_operator.post(
        "/api/gaia/warning/u/",
        json=payload,
    )
    assert response.status_code == 202

    async with db.scoped_session() as session:
        warnings = await GaiaWarning.get_multiple(session)
        assert warnings[0].title == title


def test_warning_update_failure(client_user: TestClient):
    response = client_user.post("/api/gaia/warning/u/")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_warning_update_success(
        client_operator: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    description = "Change the description"
    payload = {
        "description": description,
    }
    response = client_operator.put(
        "/api/gaia/warning/u/1",
        json=payload,
    )
    assert response.status_code == 202

    async with db.scoped_session() as session:
        warnings = await GaiaWarning.get_multiple(session)
        failed = True
        for warning in warnings:
            if warning.description == description:
                failed = False
                break
        assert not failed


@pytest.mark.asyncio
async def test_warning_mark_seen_success(
        client_user: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client_user.post("/api/gaia/warning/u/1/mark_as_seen",)
    assert response.status_code == 202

    async with db.scoped_session() as session:
        warnings = await GaiaWarning.get_multiple(session)
        failed = True
        for warning in warnings:
            if warning.seen:
                failed = False
                break
        assert not failed


@pytest.mark.asyncio
async def test_warning_mark_solved_success(
        client_user: TestClient,
        db: AsyncSQLAlchemyWrapper,
):
    response = client_user.post("/api/gaia/warning/u/1/mark_as_solved",)
    assert response.status_code == 202

    async with db.scoped_session() as session:
        warnings = await GaiaWarning.get_multiple(session, show_solved=True)
        failed = True
        for warning in warnings:
            if warning.solved:
                failed = False
                break
        assert not failed
