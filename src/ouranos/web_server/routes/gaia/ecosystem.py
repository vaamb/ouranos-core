from __future__ import annotations

import typing as t

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import ActuatorTurnTo, HardwareTypeNames, ManagementFlags

from ouranos.core import validate
from ouranos.core.utils import DispatcherFactory, timeWindow
from ouranos.core.database.models import Ecosystem, EnvironmentParameter, Light
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.common_queries import (
    ecosystems_uid_q, sensor_level_q
)


router = APIRouter(
    prefix="/ecosystem",
    responses={404: {"description": "Not found"}},
    tags=["gaia/ecosystem"],
)


id_query = Query(description="An ecosystem id, either its uid or its name")
env_parameter_query = Query(
    default=None, description="The environment parameter targeted. Leave empty "
                              "to select them all")


async def ecosystem_or_abort(
        session: AsyncSession,
        ecosystem_id: str,
) -> Ecosystem:
    ecosystem = await Ecosystem.get(session=session, ecosystem_id=ecosystem_id)
    if ecosystem:
        return ecosystem
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("", response_model=list[validate.gaia.ecosystem])
async def get_ecosystems(
        ecosystems_id: t.Optional[list[str]] = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session),
):
    ecosystems = await Ecosystem.get_multiple(
        session=session, ecosystems=ecosystems_id)
    return ecosystems


@router.post("/u", dependencies=[Depends(is_operator)])
async def create_ecosystem(
        payload: validate.gaia.ecosystem_creation = Body(
            description="Information about the new ecosystem"),
        session: AsyncSession = Depends(get_session)
):
    await Ecosystem.create(session, payload.dict())


@router.get("/u/{id}", response_model=validate.gaia.ecosystem)
async def get_ecosystem(
        id: str = id_query,
        session: AsyncSession = Depends(get_session)
):
    ecosystem = await ecosystem_or_abort(session, id)
    return ecosystem


@router.put("/u/{id}", dependencies=[Depends(is_operator)])
async def update_ecosystem(
        id: str = id_query,
        payload: validate.gaia.ecosystem_creation = Body(
            description="Updated information about the ecosystem"),
        session: AsyncSession = Depends(get_session)
):
    ecosystem = await ecosystem_or_abort(session, id)
    await Ecosystem.update(session, payload.dict(), ecosystem.uid)


@router.delete("/u/{id}", dependencies=[Depends(is_operator)])
async def delete_ecosystem(
        id: str = id_query,
        session: AsyncSession = Depends(get_session)
):
    ecosystem = await ecosystem_or_abort(session, id)
    await Ecosystem.delete(session, ecosystem.uid)


@router.get("/managements_available")
async def get_managements_available():
    return [
        {"name": management.name, "value": management.value}
        for management in ManagementFlags
    ]


@router.get("/management", response_model=list[validate.gaia.ecosystem_management])
async def get_ecosystems_management(
        ecosystems_id: t.Optional[list[str]] = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await Ecosystem.get_multiple(session, ecosystems_id)
    response = [
        await ecosystem.functionalities(session)
        for ecosystem in ecosystems
    ]
    return response


# TODO: use functionality
@router.get("/u/{id}/management", response_model=validate.gaia.ecosystem_management)
async def get_ecosystem_management(
        id: str = id_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await ecosystem.functionalities(session)
    return response


@router.get("/sensors_skeleton")
async def get_ecosystems_sensors_skeleton(
        ecosystems_id: t.Optional[list[str]] = ecosystems_uid_q,
        level: t.Optional[list[str]] = sensor_level_q,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await Ecosystem.get_multiple(session, ecosystems_id)
    response = [
        await ecosystem.sensors_data_skeleton(session, time_window, level)
        for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{id}/sensors_skeleton")
async def get_ecosystem_sensors_skeleton(
        id: str = id_query,
        level: t.Optional[list[str]] = sensor_level_q,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await ecosystem.sensors_data_skeleton(
        session, time_window, level
    )
    return response


@router.get("/light", response_model=list[validate.gaia.ecosystem_light])
async def get_ecosystems_light(
        ecosystems_id: t.Optional[list[str]] = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session)
):
    lights = await Light.get_multiple(session, ecosystems_id)
    return lights


@router.get("/u/{id}/light", response_model=validate.gaia.ecosystem_light)
async def get_ecosystem_light(
        id: str = id_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    light = await Light.get(session, ecosystem.uid)
    return light


@router.get("/environment_parameters", response_model=list[validate.gaia.environment_parameter])
async def get_ecosystems_environment_parameters(
        ecosystems_id: t.Optional[list[str]] = ecosystems_uid_q,
        parameters: t.Optional[list[str]] = env_parameter_query,
        session: AsyncSession = Depends(get_session)
):
    return await EnvironmentParameter.get_multiple(
        session, ecosystems_id, parameters)


@router.get("/u/{id}/environment_parameters", response_model=validate.gaia.environment_parameter)
async def get_ecosystem_environment_parameters(
        id: str = id_query,
        parameters: t.Optional[list[str]] = env_parameter_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    return await EnvironmentParameter.get_multiple(
        session, [ecosystem.uid, ], parameters)


@router.get("/current_data")
async def get_ecosystems_current_data(
        ecosystems_id: t.Optional[list[str]] = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await Ecosystem.get_multiple(
        session=session, ecosystems=ecosystems_id)
    return [ecosystem.current_data() for ecosystem in ecosystems]


@router.get("/u/{id}/current_data")
async def get_ecosystem_current_data(
        id: str = id_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    return ecosystem.current_data()


@router.get("/u/{id}/turn_actuator", dependencies=[Depends(is_operator)])
async def turn_actuator(
        id: str = id_query,
        actuator: HardwareTypeNames = Query(
            description="The type of actuator"),
        mode: ActuatorTurnTo = Query(
            description="The mode to turn the actuator to"),
        countdown: float = Query(
            default=0.0,
            description="Time before turning the actuator to the required mode"
        ),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    dispatcher = DispatcherFactory.get("application")
    await ecosystem.turn_actuator(
        dispatcher, actuator, mode, countdown)
    return validate.common.simple_message(
        msg=f"Turned {ecosystem.name}'s {actuator} to mode '{mode}'"
    )
