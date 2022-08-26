import typing as t

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import router
from src import api
from src.api.utils import timeWindow
from src.app.auth import is_operator
from src.app.dependencies import get_session, get_time_window
from src.app.routes.utils import empty_result


async def ecosystems_or_abort(session, ecosystems):
    ecosystems_qo = await api.gaia.get_ecosystems(
        session=session, ecosystems=ecosystems
    )
    if ecosystems_qo:
        return ecosystems_qo
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


def assert_single_ecosystem_id(ecosystem_id):
    if "all" in ecosystem_id or len(ecosystem_id.split(",")) > 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="`ecosystem_id` should be a single ecosystem name or uid"
        )


@router.get("/ecosystem")
async def get_ecosystems(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await api.gaia.get_ecosystems(
        session=session, ecosystems=ecosystems_id
    )
    response = [api.gaia.get_ecosystem_info(
        session, ecosystem
    ) for ecosystem in ecosystems]
    if response:
        return response
    return empty_result([])


@router.post("/ecosystem/u", dependencies=[Depends(is_operator)])
async def post_ecosystem(session=Depends(get_session)):
    pass


@router.get("/ecosystem/u/<id>")
async def get_ecosystem(ecosystem_id: str, session: AsyncSession = Depends(get_session)):
    assert_single_ecosystem_id(ecosystem_id)
    ecosystem = await ecosystems_or_abort(session, ecosystem_id)
    response = api.gaia.get_ecosystem_info(session, ecosystem[0])
    return response


@router.put("/ecosystem/u/<id>", dependencies=[Depends(is_operator)])
async def put_ecosystem(ecosystem_id: str, session=Depends(get_session)):
    assert_single_ecosystem_id(ecosystem_id)
    ecosystem = await ecosystems_or_abort(session, ecosystem_id)
    # TODO


@router.delete("/ecosystem/u/<id>", dependencies=[Depends(is_operator)])
async def delete_ecosystem(ecosystem_id: str, session=Depends(get_session)):
    assert_single_ecosystem_id(ecosystem_id)
    ecosystem = await ecosystems_or_abort(session, ecosystem_id)
    # TODO


@router.get("/ecosystem/management")
async def get_ecosystems_management(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await ecosystems_or_abort(session, ecosystems_id)
    response = [api.gaia.get_ecosystem_management(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/management")
async def get_ecosystem_management(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_ecosystem_id(ecosystem_id)
    ecosystem = await ecosystems_or_abort(ecosystem_id)
    response = api.gaia.get_ecosystem_management(
        session, ecosystem[0]
    )
    return response


@router.get("/ecosystem/sensors_skeleton")
async def get_ecosystems_sensors_skeleton(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        level: t.Optional[list[str]] = Query(default=None),
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await ecosystems_or_abort(session, ecosystems_id)
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
    assert_single_ecosystem_id(ecosystem_id)
    ecosystem = await ecosystems_or_abort(session, ecosystem_id)
    if ecosystem:
        response = api.gaia.get_ecosystem_sensors_data_skeleton(
            session, ecosystem[0], time_window, level
        )
        return response


@router.get("/ecosystem/light")
async def get_ecosystems_light(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await ecosystems_or_abort(session, ecosystems_id)
    response = [api.gaia.get_light_info(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/light")
async def get_ecosystem_light(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_ecosystem_id(ecosystem_id)
    ecosystem = await ecosystems_or_abort(session, ecosystem_id)
    if ecosystem:
        response = api.gaia.get_light_info(session, ecosystem[0])
        return response


@router.get("/ecosystem/environment_parameters")
async def get_ecosystems_environment_parameters(
        ecosystems_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await ecosystems_or_abort(session, ecosystems_id)
    response = [api.gaia.get_environmental_parameters(
        session, ecosystem
    ) for ecosystem in ecosystems]
    return response


@router.get("/ecosystem/u/<id>/environment_parameters")
async def get_ecosystems_environment_parameters(
        ecosystem_id: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_ecosystem_id(ecosystem_id)
    ecosystem = await ecosystems_or_abort(session, ecosystem_id)
    if ecosystem:
        response = api.gaia.get_environmental_parameters(
            session, ecosystem[0]
        )
        return response
