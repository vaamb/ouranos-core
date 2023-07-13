from datetime import datetime, time, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.config import ConfigDict
from ouranos.core.config.consts import LOGIN_NAME
from ouranos.core.database.models.app import User
from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, GaiaWarning, Hardware,
    HealthRecord, Lighting, SensorRecord)
from ouranos.core.database.models.memory import SensorDbCache, SystemDbCache
from ouranos.core.database.models.system import SystemRecord
from ouranos.web_server.auth import SessionInfo
from ouranos.web_server.factory import create_app

from ..data.gaia import *
from ..data.system import system_dict
from ..data.users import admin, operator, user


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_ecosystems(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        await Engine.create(session, engine_dict)

        full_ecosystem_dict = {
            **ecosystem_dict,
            "day_start": sky["day"],
            "night_start": sky["night"],
        }
        await Ecosystem.create(session, full_ecosystem_dict)

        environment_parameter = {
            "ecosystem_uid": ecosystem_uid,
            **climate
        }
        await EnvironmentParameter.create(session, environment_parameter)

        adapted_light_data = light_data.copy()
        adapted_light_data["ecosystem_uid"] = ecosystem_uid
        await Lighting.create(session, adapted_light_data)

        adapted_hardware_data = hardware_data.copy()
        adapted_hardware_data.pop("multiplexer_model")
        adapted_hardware_data["ecosystem_uid"] = ecosystem_uid
        await Hardware.create(session, adapted_hardware_data)

        adapted_sensor_record = {
            "ecosystem_uid": ecosystem_uid,
            "sensor_uid": sensor_record["sensor_uid"],
            "measure": measure_record["measure"],
            "timestamp": sensors_data["timestamp"],
            "value": float(measure_record["value"]),
        }
        await SensorDbCache.insert_data(session, adapted_sensor_record)

        adapted_sensor_record["timestamp"] = (
                sensors_data["timestamp"] - timedelta(hours=1))
        await SensorRecord.create_records(session, adapted_sensor_record)

        adapted_health_data = health_data.copy()
        adapted_health_data["health_index"] = adapted_health_data["index"]
        adapted_health_data.pop("index")
        adapted_health_data["ecosystem_uid"] = ecosystem_uid
        await HealthRecord.create_records(session, adapted_health_data)

        await GaiaWarning.create(session, gaia_warning)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_system(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        adapted_system_record = system_dict.copy()
        await SystemDbCache.insert_data(session, adapted_system_record)

        adapted_system_record["timestamp"] = (
                system_dict["timestamp"] - timedelta(hours=1))
        await SystemRecord.create_records(session, adapted_system_record)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def users(db: AsyncSQLAlchemyWrapper):
    users_dict: dict[str, int] = {}
    async with db.scoped_session() as session:
        for u in (admin, operator, user):
            user_info = {
                "email": f"{u.username}@fakemail.com",
                "firstname": u.firstname,
                "lastname": u.lastname,
                "role": u.role.value
            }
            await User.create(session, u.username, u.password, **user_info)
            usr = await User.get(session, u.username)
            users_dict[u.role.value] = usr.id
    return users_dict


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
