from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

import gaia_validators as gv

from ouranos.core.config import ConfigDict
from ouranos.core.config.consts import LOGIN_NAME
from ouranos.core.database.models.app import (
    CalendarEvent, User, Service, ServiceName, WikiArticle, WikiArticlePicture,
    WikiTopic)
from ouranos.core.database.models.gaia import (
    ActuatorRecord, ActuatorState, Ecosystem, Engine, EnvironmentParameter,
    GaiaWarning, Hardware, HealthRecord, Lighting, SensorDataCache,
    SensorDataRecord)
from ouranos.core.database.models.system import (
    System, SystemDataCache, SystemDataRecord)
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.web_server.auth import SessionInfo
from ouranos.web_server.factory import create_app

from tests.data.app import (
    calendar_event, wiki_article_content, wiki_article_name, wiki_picture_content,
    wiki_picture_name, wiki_topic_name)
from tests.data.auth import admin, operator, user
import tests.data.gaia as g_data
from tests.data.system import system_dict, system_data_dict
from tests.utils import MockAsyncDispatcher


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_ecosystems(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        engine = g_data.engine_dict.copy()
        uid = engine.pop("uid")
        await Engine.create(session, uid=uid, values=engine)

        ecosystem = {**g_data.ecosystem_dict}
        uid = ecosystem.pop("uid")
        await Ecosystem.create(session, uid=uid, values=ecosystem)

        environment_parameter = g_data.climate.copy()
        parameter = environment_parameter.pop("parameter")
        await EnvironmentParameter.create(
            session, ecosystem_uid=uid, parameter=parameter, values=environment_parameter)

        await Lighting.create(
            session,
            ecosystem_uid=uid,
            values={
                "span": g_data.sky["span"],
                "lighting": g_data.sky["lighting"],
                "target_id": None,
                "day": g_data.sky["day"],
                "night": g_data.sky["night"],
                **g_data.light_data,
            }
        )

        hardware = gv.HardwareConfig(**g_data.hardware_data).model_dump()
        hardware_uid = hardware.pop("uid")
        hardware.pop("multiplexer_model")
        hardware["ecosystem_uid"] = uid
        await Hardware.create(session, uid=hardware_uid, values=hardware)

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

        actuator_state = {
            "active": g_data.actuator_record.active,
            "mode": g_data.actuator_record.mode,
            "status": g_data.actuator_record.status,
            "level": g_data.actuator_record.level,
        }
        await ActuatorState.create(
            session, ecosystem_uid=uid, type=g_data.actuator_record.type,
            values=actuator_state)

        actuator_state["ecosystem_uid"] = uid
        actuator_state["type"] = g_data.actuator_record.type
        actuator_state["timestamp"] = g_data.actuator_record.timestamp
        await ActuatorRecord.create_records(session, actuator_state)

        # TODO: fix when health data is reimplemented
        #adapted_health_data = {
        #    "ecosystem_uid": g_data.ecosystem_uid,
        #    "green": g_data.health_data.green,
        #    "necrosis": g_data.health_data.necrosis,
        #    "health_index": g_data.health_data.index,
        #    "timestamp": g_data.health_data.timestamp,
        #}
        #await HealthRecord.create_records(session, adapted_health_data)

        await GaiaWarning.create(
            session, ecosystem_uid=g_data.ecosystem_uid, values=g_data.gaia_warning)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_system(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        system = system_dict.copy()
        uid = system.pop("uid")
        await System.create(session, uid=uid, values=system)

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
                "username": u.username,
                "password": u.password,
                "email": f"{u.username}@fakemail.com",
                "firstname": u.firstname,
                "lastname": u.lastname,
                "role": u.role.value
            }
            await User.create(session, values=user_info)
            usr = await User.get_by(session, username=u.username)
            users_dict[u.role.value] = usr.id
    return users_dict


@pytest_asyncio.fixture(scope="module", autouse=True)
async def enable_services(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        for service_name in ServiceName:
            await Service.update(session, name=service_name, values={"status": True})


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_events(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        await CalendarEvent.create(session, creator_id=user.id, values=calendar_event)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def add_wiki(db: AsyncSQLAlchemyWrapper):
    async with db.scoped_session() as session:
        await WikiTopic.create(session, name=wiki_topic_name)
        topic = await WikiTopic.get(session, name=wiki_topic_name)
        await topic.create_template(wiki_article_content)

        await WikiArticle.create(
            session, topic=wiki_topic_name, name=wiki_article_name,
            content=wiki_article_content, author_id=operator.id)
        await WikiArticlePicture.create(
            session, topic=wiki_topic_name, article=wiki_article_name,
            name=wiki_picture_name, content=wiki_picture_content,
            author_id=operator.id)


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


@pytest.fixture(scope="module")
def mock_dispatcher_module():
    mock_dispatcher = MockAsyncDispatcher("application-internal")
    DispatcherFactory._DispatcherFactory__dispatchers["application-internal"] = mock_dispatcher
    return mock_dispatcher


@pytest.fixture(scope="function")
def mock_dispatcher(mock_dispatcher_module):
    mock_dispatcher_module.clear_store()
    return mock_dispatcher_module
