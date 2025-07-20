import pytest_asyncio

import gaia_validators as gv
from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.gaia import Ecosystem, Engine, Hardware

import tests.data.gaia as g_data


class EngineAware:
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_engine(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            engine = g_data.engine_dict.copy()
            uid = engine.pop("uid")
            await Engine.create(session, uid=uid, values=engine)


class EcosystemAware(EngineAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_ecosystem(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            ecosystem = {**g_data.ecosystem_dict}
            uid = ecosystem.pop("uid")
            await Ecosystem.update_or_create(session, uid=uid, values=ecosystem)


class HardwareAware(EcosystemAware):
    @pytest_asyncio.fixture(scope="class", autouse=True)
    async def add_hardware(self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            hardware_config = [g_data.hardware_data.copy(), g_data.camera_config.copy()]
            for hardware in hardware_config:
                hardware = gv.HardwareConfig(**hardware).model_dump()
                hardware_uid = hardware.pop("uid")
                hardware["ecosystem_uid"] = g_data.ecosystem_uid
                del hardware["multiplexer_model"]
                await Hardware.create(session, uid=hardware_uid, values=hardware)
