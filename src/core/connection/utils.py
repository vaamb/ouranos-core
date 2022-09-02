import typing as t

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import api
from src.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, Hardware, Light
)


async def update_engine_or_create_it(
        session: AsyncSession,
        engine_info: t.Optional[dict] = None,
        uid: t.Optional[str] = None,
) -> Engine:
    engine_info = engine_info or {}
    uid = uid or engine_info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    engine = await api.gaia.get_engine(session, uid)
    if not engine:
        engine_info["uid"] = uid
        engine = await api.gaia.create_engine(session, engine_info)
    elif engine_info:
        await api.gaia.update_engine(session, engine_info, uid)
    return engine


async def update_ecosystem_or_create_it(
        session: AsyncSession,
        ecosystem_info: t.Optional[dict] = None,
        uid: t.Optional[str] = None,
) -> Ecosystem:
    ecosystem_info = ecosystem_info or {}
    uid = uid or ecosystem_info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    ecosystem = await api.gaia.get_ecosystem(session, uid)
    if not ecosystem:
        ecosystem_info["uid"] = uid
        ecosystem = await api.gaia.create_ecosystem(session, ecosystem_info)
    elif ecosystem_info:
        await api.gaia.update_ecosystem(session, ecosystem_info, uid)
    return ecosystem


async def update_hardware_or_create_it(
        session: AsyncSession,
        hardware_info: t.Optional[dict] = None,
        uid: t.Optional[str] = None,
) -> Hardware:
    hardware_info = hardware_info or {}
    uid = uid or hardware_info.pop("uid", None)
    if not uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    hardware = await api.gaia.get_hardware(session, uid)
    if not hardware:
        hardware_info["uid"] = uid
        # TODO: solve
        hardware_info.pop("measure", None)
        hardware = await api.gaia.create_hardware(session, hardware_info)
    elif hardware_info:
        await api.gaia.update_hardware(session, hardware_info, uid)
    return hardware


async def update_environment_parameter_or_create_it(
        session: AsyncSession,
        uid: t.Optional[str] = None,
        parameter: t.Optional[str] = None,
        parameter_info: t.Optional[dict] = None,
) -> EnvironmentParameter:
    parameter_info = parameter_info or {}
    uid = uid or parameter_info.pop("uid", None)
    parameter = parameter or parameter_info.pop("parameter", None)
    if not (uid or parameter):
        raise ValueError(
            "Provide uid and parameter either as a argument or as a key in the "
            "updated info"
        )
    environment_parameter = await api.gaia.get_environmental_parameter(
        session, uid=uid, parameter=parameter
    )
    if not environment_parameter:
        parameter_info["ecosystem_uid"] = uid
        parameter_info["parameter"] = parameter
        environment_parameter = await api.gaia.create_environmental_parameter(
            session, parameter_info
        )
    elif parameter_info:
        await api.gaia.update_environmental_parameter(
            session, parameter_info, uid
        )
    return environment_parameter


async def update_light_or_create_it(
        session: AsyncSession,
        light_info: t.Optional[dict] = None,
        ecosystem_uid: t.Optional[str] = None,
) -> Light:
    light_info = light_info or {}
    ecosystem_uid = ecosystem_uid or light_info.pop("ecosystem_uid", None)
    if not ecosystem_uid:
        raise ValueError(
            "Provide uid either as an argument or as a key in the updated info"
        )
    light = await api.gaia.get_light(session, ecosystem_uid)
    if not light:
        light_info["ecosystem_uid"] = ecosystem_uid
        light = await api.gaia.create_light(session, light_info)
    elif light_info:
        await api.gaia.update_light(session, light_info, ecosystem_uid)
    return light
