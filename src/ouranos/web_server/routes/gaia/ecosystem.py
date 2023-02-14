from __future__ import annotations

import typing as t

from fastapi import Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.sdk import api
from ouranos.sdk.api.utils import timeWindow
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.gaia import router
from ouranos.web_server.routes.utils import assert_single_uid


if t.TYPE_CHECKING:
    from ouranos.core.database.models import Ecosystem


async def ecosystem_or_abort(
        session: AsyncSession,
        ecosystem_id: str,
) -> "Ecosystem":
    ecosystem = await api.ecosystem.get(
        session=session, ecosystem_id=ecosystem_id
    )
    if ecosystem:
        return ecosystem
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("/ecosystem", response_model=list[validate.gaia.ecosystem])
async def get_ecosystems(
        ecosystems: list[str] | None = Query(default=None),
        session: AsyncSession = Depends(get_session),
):
    ecosystems_qo = await api.ecosystem.get_multiple(
        session=session, ecosystems=ecosystems
    )
    return ecosystems_qo


@router.post("/ecosystem/u", dependencies=[Depends(is_operator)])
async def create_ecosystem(
        payload: validate.gaia.ecosystem_creation = Body(),
        session: AsyncSession = Depends(get_session)
):
    await api.ecosystem.create(session, payload.dict())


@router.get("/ecosystem/u/<id>", response_model=validate.gaia.ecosystem)
async def get_ecosystem(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    return ecosystem


@router.put("/ecosystem/u/<id>", dependencies=[Depends(is_operator)])
async def update_ecosystem(
        ecosystem_id: str,
        payload: validate.gaia.ecosystem_creation = Body(),
        session: AsyncSession = Depends(get_session)
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    await api.ecosystem.update(session, payload.dict(), ecosystem.uid)


@router.delete("/ecosystem/u/<id>", dependencies=[Depends(is_operator)])
async def delete_ecosystem(ecosystem_id: str, session=Depends(get_session)):
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    await api.ecosystem.delete(session, ecosystem.uid)


@router.get("/ecosystem/management", response_model=list[validate.gaia.ecosystem_management])
async def get_ecosystems_management(
        ecosystems: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await api.ecosystem.get_multiple(session, ecosystems)
    response = [await api.ecosystem.get_management(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/management", response_model=validate.gaia.ecosystem_management)
async def get_ecosystem_management(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    response = await api.ecosystem.get_management(
        session, ecosystem
    )
    return response


@router.get("/ecosystem/sensors_skeleton")
async def get_ecosystems_sensors_skeleton(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        level: t.Optional[list[str]] = Query(default=None),
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await api.ecosystem.get_multiple(session, ecosystems_id)
    response = [await api.ecosystem.get_sensors_data_skeleton(
        session, ecosystem, time_window, level
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/sensors_skeleton")
async def get_ecosystem_sensors_skeleton(
        ecosystem_id: str,
        level: t.Optional[list[str]] = Query(default=None),
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    response = await api.ecosystem.get_sensors_data_skeleton(
        session, ecosystem, time_window, level
    )
    return response


@router.get("/ecosystem/light", response_model=list[validate.gaia.ecosystem_light])
async def get_ecosystems_light(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    lights = await api.light.get_multiple(session, ecosystems_id)
    return lights


@router.get("/ecosystem/u/<id>/light", response_model=validate.gaia.ecosystem_light)
async def get_ecosystem_light(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    light = await api.light.get(session, ecosystem_id)
    return light


@router.get("/ecosystem/environment_parameters", response_model=list[validate.gaia.environment_parameter])
async def get_ecosystems_environment_parameters(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        parameters: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    env_parameters = await api.environmental_parameter.get_multiple(
        session, ecosystems_id, parameters
    )
    return [parameter.to_dict() for parameter in env_parameters]


@router.get("/ecosystem/u/<id>/environment_parameters", response_model=validate.gaia.environment_parameter)
async def get_ecosystems_environment_parameters(
        ecosystem_id: str,
        parameters: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    env_parameters = await api.environmental_parameter.get(
        session, ecosystem_id, parameters
    )
    return [parameter.to_dict() for parameter in env_parameters]
