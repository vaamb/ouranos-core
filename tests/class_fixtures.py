from datetime import timedelta

import pytest_asyncio

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

import gaia_validators as gv

from ouranos.core.database.models.app import (
    CalendarEvent, User, Service, ServiceName, WikiArticle, WikiPicture,
    WikiTopic)
from ouranos.core.database.models.gaia import (
    ActuatorRecord, ActuatorState, Ecosystem, Engine, EnvironmentParameter,
    GaiaWarning, Hardware, NycthemeralCycle, Plant, SensorDataCache, SensorDataRecord)
from ouranos.core.database.models.system import (
    System, SystemDataCache, SystemDataRecord)

import tests.data.app as a_data
from tests.data.auth import admin, operator, user
import tests.data.gaia as g_data
from tests.data.system import system_dict, system_data_dict


class EngineAware:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_engine(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            engine = g_data.engine_dict.copy()
            uid = engine.pop("uid")
            await Engine.create(session, uid=uid, values=engine)


class EcosystemAware(EngineAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_ecosystem(self, db: AsyncSQLAlchemyWrapper, add_engine):
        async with db.scoped_session() as session:
            ecosystem = {**g_data.ecosystem_dict}
            uid = ecosystem.pop("uid")
            await Ecosystem.create(session, uid=uid, values=ecosystem)


class EnvironmentAware(EcosystemAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_environment_parameters(self, db: AsyncSQLAlchemyWrapper, add_ecosystem):
        async with db.scoped_session() as session:
            uid = g_data.ecosystem_uid
            environment_parameter = g_data.climate.copy()
            parameter = environment_parameter.pop("parameter")
            await EnvironmentParameter.create(
                session, ecosystem_uid=uid, parameter=parameter, values=environment_parameter)

            await NycthemeralCycle.create(
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


class HardwareAware(EcosystemAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_hardware(self, db: AsyncSQLAlchemyWrapper, add_ecosystem):
        async with db.scoped_session() as session:
            hardware_config = [g_data.hardware_data, g_data.camera_config]
            for hardware in hardware_config:
                hardware = gv.HardwareConfig(**hardware).model_dump()
                hardware_uid = hardware.pop("uid")
                hardware["ecosystem_uid"] = g_data.ecosystem_uid
                del hardware["multiplexer_model"]
                del hardware["groups"]
                await Hardware.create(session, uid=hardware_uid, values=hardware)

            plant_data = g_data.plant_data.copy()
            uid = plant_data.pop("uid")
            plant_data["ecosystem_uid"] = g_data.ecosystem_uid
            await Plant.create(session, uid=uid, values=plant_data)


class SensorsAware(HardwareAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_sensors(self, db: AsyncSQLAlchemyWrapper, add_hardware):
        async with db.scoped_session() as session:
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
            await SensorDataRecord.create_multiple(session, adapted_sensor_record)


class ActuatorsAware(HardwareAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_actuators(self, db: AsyncSQLAlchemyWrapper, add_hardware):
        async with db.scoped_session() as session:
            uid = g_data.ecosystem_uid
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
            await ActuatorRecord.create_multiple(session, actuator_state)


class GaiaWarningsAware(EcosystemAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_gaia_warnings(self, db: AsyncSQLAlchemyWrapper, add_ecosystem):
        async with db.scoped_session() as session:
            await GaiaWarning.create(
                session, ecosystem_uid=g_data.ecosystem_uid, values=g_data.gaia_warning)


class SystemAware:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_system(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            system = system_dict.copy()
            uid = system.pop("uid")
            await System.create(session, uid=uid, values=system)

            adapted_system_record = system_data_dict.copy()
            await SystemDataCache.insert_data(session, adapted_system_record)

            adapted_system_record["timestamp"] = (
                    system_data_dict["timestamp"] - timedelta(hours=1))
            await SystemDataRecord.create_multiple(session, adapted_system_record)


class UsersAware:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def users(self, db: AsyncSQLAlchemyWrapper):
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


class ServicesEnabled:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def enable_services(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            for service_name in ServiceName:
                await Service.update(session, name=service_name, values={"status": True})


class EventsAware:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_events(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await CalendarEvent.create(
                session, creator_id=user.id, values=a_data.calendar_event_public)
            await CalendarEvent.create(
                session, creator_id=user.id, values=a_data.calendar_event_users)


class WikiAware:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_wiki(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await WikiTopic.create(
                session,
                name=a_data.wiki_topic_name,
                values={
                    "description": "Useless",
                },
            )

            topic = await WikiTopic.get(session, name=a_data.wiki_topic_name)
            await topic.create_template(a_data.wiki_article_content)

            await WikiArticle.create(
                session,
                topic_name=a_data.wiki_topic_name,
                name=a_data.wiki_article_name,
                values={
                    "content": a_data.wiki_article_content,
                    "author_id": operator.id,
                },
            )

            await WikiPicture.create(
                session,
                topic_name=a_data.wiki_topic_name,
                article_name=a_data.wiki_article_name,
                name=a_data.wiki_picture_name,
                values={
                    "content": a_data.wiki_picture_content,
                    "extension": ".png"
                },
            )
