from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

import gaia_validators as gv

from ouranos.core.config import ConfigDict
from ouranos.core.config.consts import LOGIN_NAME
from ouranos.core.database.models.app import CalendarEvent, User
from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, GaiaWarning, Hardware,
    HealthRecord, Lighting, SensorDataCache, SensorDataRecord)
from ouranos.core.database.models.system import (
    System, SystemDataCache, SystemDataRecord)
from ouranos.web_server.auth import SessionInfo
from ouranos.web_server.factory import create_app

import tests.data.gaia as g_data
from tests.data.app import calendar_event
from tests.data.auth import admin, operator, user
from tests.data.system import system_dict, system_data_dict


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_ecosystems(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        await Engine.create(session, g_data.engine_dict)

        full_ecosystem_dict = {
            **g_data.ecosystem_dict,
            "day_start": g_data.sky["day"],
            "night_start": g_data.sky["night"],
        }
        await Ecosystem.create(session, full_ecosystem_dict)

        environment_parameter = {
            "ecosystem_uid": g_data.ecosystem_uid,
            **g_data.climate
        }
        await EnvironmentParameter.create(session, environment_parameter)

        adapted_light_data = g_data.light_data.copy()
        adapted_light_data["ecosystem_uid"] = g_data.ecosystem_uid
        await Lighting.create(session, adapted_light_data)

        adapted_hardware_data = gv.HardwareConfig(**g_data.hardware_data).model_dump()
        adapted_hardware_data.pop("multiplexer_model")
        adapted_hardware_data["ecosystem_uid"] = g_data.ecosystem_uid
        await Hardware.create(session, adapted_hardware_data)

        adapted_sensor_record = {
            "ecosystem_uid": g_data.ecosystem_uid,
            "sensor_uid": g_data.sensor_record.sensor_uid,
            "measure": g_data.sensor_record.measure,
            "timestamp": g_data.timestamp_now,
            "value": g_data.sensor_record.value,
        }
        await SensorDataCache.insert_data(session, adapted_sensor_record)

        adapted_sensor_record["timestamp"] = (
                g_data.sensors_data["timestamp"] - timedelta(hours=1))
        await SensorDataRecord.create_records(session, adapted_sensor_record)

        adapted_health_data = {
            "ecosystem_uid": g_data.ecosystem_uid,
            "green": g_data.health_data.green,
            "necrosis": g_data.health_data.necrosis,
            "health_index": g_data.health_data.index,
            "timestamp": g_data.health_data.timestamp,
        }
        await HealthRecord.create_records(session, adapted_health_data)

        await GaiaWarning.create(
            session, ecosystem_uid=g_data.ecosystem_uid, values=g_data.gaia_warning)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_system(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        await System.create(session, system_dict)

        adapted_system_record = system_data_dict.copy()
        await SystemDataCache.insert_data(session, adapted_system_record)

        adapted_system_record["timestamp"] = (
                system_data_dict["timestamp"] - timedelta(hours=1))
        await SystemDataRecord.create_records(session, adapted_system_record)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def users(db: AsyncSQLAlchemyWrapper):
    users_dict: dict[str, int] = {}
    async with db.scoped_session() as session:
        for u in (admin, operator, user):
            user_info = {
                "id": u.id,
                "email": f"{u.username}@fakemail.com",
                "firstname": u.firstname,
                "lastname": u.lastname,
                "role": u.role.value
            }
            await User.create(session, u.username, u.password, **user_info)
            usr = await User.get(session, u.username)
            users_dict[u.role.value] = usr.id
    return users_dict


@pytest_asyncio.fixture(scope="module", autouse=True)
async def events(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        await CalendarEvent.create(session, creator_id=user.id, values=calendar_event)


@pytest.fixture(scope="module")
def app(config: ConfigDict):
    return create_app(config)


@pytest.fixture(scope="module")
def base_client(app: FastAPI):
    return TestClient(app)


@pytest.fixture(scope="function")
def client(base_client: TestClient):
    base_client.cookies = None
    return base_client


def get_user_cookie(user_id) -> dict:
    payload = SessionInfo(id="session_id", user_id=user_id, remember=True)
    token = payload.to_token()
    return {LOGIN_NAME.COOKIE.value: token}


@pytest.fixture(scope="function")
def client_user(
        client: TestClient,
        users: dict[str, int],
):
    client.cookies = get_user_cookie(users["User"])
    return client


@pytest.fixture(scope="function")
def client_operator(
        client: TestClient,
        users: dict[str, int],
):
    client.cookies = get_user_cookie(users["Operator"])
    return client


@pytest.fixture(scope="function")
def client_admin(
        client: TestClient,
        users: dict[str, int],
):
    client.cookies = get_user_cookie(users["Administrator"])
    return client
