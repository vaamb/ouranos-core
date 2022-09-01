from __future__ import annotations

import typing as t

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import router
from ..utils import assert_single_uid
from src import api
from src.api.utils import timeWindow
from src.app.auth import is_operator
from src.app.dependencies import get_session, get_time_window
from src.database.models.gaia import Ecosystem


async def ecosystem_or_abort(
        session: AsyncSession,
        ecosystem_id: str,
) -> Ecosystem:
    ecosystem = await api.gaia.get_ecosystem(
        session=session, ecosystem_id=ecosystem_id
    )
    if ecosystem:
        return ecosystem
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("/ecosystem")
async def get_ecosystems(
        ecosystems: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session),
) -> list[dict[str: str]]:
    ecosystems_qo = await api.gaia.get_ecosystems(
        session=session, ecosystems=ecosystems
    )
    response = [api.gaia.get_ecosystem_info(
        session, ecosystem
    ) for ecosystem in ecosystems_qo]
    return response


@router.post("/ecosystem/u", dependencies=[Depends(is_operator)])
async def create_ecosystem(session: AsyncSession = Depends(get_session)) -> None:
    pass


@router.get("/ecosystem/u/<id>")
async def get_ecosystem(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    response = api.gaia.get_ecosystem_info(session, ecosystem)
    return response


@router.put("/ecosystem/u/<id>", dependencies=[Depends(is_operator)])
async def update_ecosystem(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    # TODO


@router.delete("/ecosystem/u/<id>", dependencies=[Depends(is_operator)])
async def delete_ecosystem(ecosystem_id: str, session=Depends(get_session)):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    # TODO


@router.get("/ecosystem/management")
async def get_ecosystems_management(
        ecosystems: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await api.gaia.get_ecosystems(session, ecosystems)
    response = [api.gaia.get_ecosystem_management(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/management")
async def get_ecosystem_management(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    response = api.gaia.get_ecosystem_management(
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
    ecosystems = await api.gaia.get_ecosystems(session, ecosystems_id)
    response = [api.gaia.get_ecosystem_sensors_data_skeleton(
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
    response = api.gaia.get_ecosystem_sensors_data_skeleton(
        session, ecosystem, time_window, level
    )
    return response


@router.get("/ecosystem/light")
async def get_ecosystems_light(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await api.gaia.get_ecosystems(session, ecosystems_id)
    response = [api.gaia.get_light_info(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/light")
async def get_ecosystem_light(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    response = api.gaia.get_light_info(session, ecosystem)
    return response


@router.get("/ecosystem/environment_parameters")
async def get_ecosystems_environment_parameters(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await api.gaia.get_ecosystems(session, ecosystems_id)
    response = [api.gaia.get_environment_parameters(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/environment_parameters")
async def get_ecosystems_environment_parameters(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(ecosystem_id)
    ecosystem = await ecosystem_or_abort(session, ecosystem_id)
    response = api.gaia.get_environment_parameters(
        session, ecosystem
    )
    return response
