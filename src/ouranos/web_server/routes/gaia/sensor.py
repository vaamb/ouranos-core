from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import gaia_validators as gv

from ouranos.core.database.models.gaia import Ecosystem, Measure, Sensor
from ouranos.core.utils import timeWindow
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.gaia.utils import (
    ecosystem_or_abort, in_config_desc, uids_desc)
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.validate.gaia.sensor import (
    EcosystemSensorData, SensorMeasureCurrentTimedValue,
    SensorMeasureHistoricTimedValue)


router = APIRouter(
    prefix="/ecosystem",
    responses={404: {"description": "Not found"}},
    tags=["gaia/ecosystem/sensor"],
)


id_desc = "An ecosystem id, either its uid or its name"


async def sensor_or_abort(
        session: AsyncSession,
        sensor_uid: str
) -> Sensor:
    sensor = await Sensor.get(session, uid=sensor_uid)
    if sensor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sensor(s) found"
        )
    return sensor


@router.get("/sensor/measures_available", response_model=list[gv.Measure])
async def get_measures_available(session: AsyncSession = Depends(get_session)):
    measures = await Measure.get_multiple(session)
    return measures


@router.get("/sensor/data/current", response_model=list[EcosystemSensorData])
async def get_measures_available(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=uids_desc)] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)]
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "values": await ecosystem.get_current_data(session)
        } for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{id}/sensor/data/current", response_model=EcosystemSensorData)
async def get_ecosystem_current_data(
        id: Annotated[str, Path(description=id_desc)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "values": await ecosystem.get_current_data(session)
    }
    return response


@router.get("/u/{id}/sensor/u/{uid}/data/{measure}/current",
            response_model=SensorMeasureCurrentTimedValue)
async def get_sensor_current_data(
        id: Annotated[str, Path(description=id_desc)],
        uid: Annotated[str, Path(description="The uid of a sensor")],
        measure: Annotated[
            str,
            Path(description="The measure for which to fetch current data"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    assert_single_uid(uid)
    await ecosystem_or_abort(session, id)
    sensor = await sensor_or_abort(session, uid)
    current_data = await sensor.get_current_data(session, measure=measure)
    if current_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This measure is not available for this sensor"
        )
    response = {
        "uid": sensor.uid,
        **current_data,
    }
    return response


@router.get("/u/{id}/sensor/u/{uid}/data/{measure}/historic",
            response_model=SensorMeasureHistoricTimedValue)
async def get_sensor_historic_data(
        id: Annotated[str, Path(description=id_desc)],
        uid: Annotated[str, Path(description="The uid of a sensor")],
        measure: Annotated[
            str,
            Path(description="The measure for which to fetch historic data"),
        ],
        time_window: Annotated[
            timeWindow,
            Depends(get_time_window(rounding=10, grace_time=60)),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    assert_single_uid(uid)
    await ecosystem_or_abort(session, id)
    sensor = await sensor_or_abort(session, uid)
    historic_data = await sensor.get_historic_data(
        session, measure=measure, time_window=time_window)
    if historic_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This measure is not available for this sensor"
        )
    response = {
        "uid": sensor.uid,
        **historic_data,
    }
    return response
