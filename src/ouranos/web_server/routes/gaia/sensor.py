from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import gaia_validators as gv

from ouranos.core.database.models.gaia import Measure, Sensor
from ouranos.core.utils import timeWindow
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.validate.gaia.sensor import (
    SensorMeasureCurrentTimedValue, SensorMeasureHistoricTimedValue)


router = APIRouter(
    prefix="/sensor",
    responses={404: {"description": "Not found"}},
    tags=["gaia/sensor"],
)


uid_param = Path(description="The uid of a sensor")


async def sensor_or_abort(
        session: AsyncSession,
        sensor_uid: str
) -> Sensor:
    sensor = await Sensor.get(session=session, uid=sensor_uid)
    if sensor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sensor(s) found"
        )
    return sensor


@router.get("/measures_available", response_model=list[gv.Measure])
async def get_measures_available(session: AsyncSession = Depends(get_session)):
    measures = await Measure.get_multiple(session)
    return measures


@router.get("/u/{uid}/data/{measure}/current", response_model=SensorMeasureCurrentTimedValue)
async def get_sensor_current_data(
        uid: str = uid_param,
        measure: str = Path(description="The measure for which to fetch current data"),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
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


@router.get("/u/{uid}/data/{measure}/historic", response_model=SensorMeasureHistoricTimedValue)
async def get_sensor_historic_data(
        uid: str = uid_param,
        measure: str = Path(description="The measure for which to fetch historic data"),
        time_window: timeWindow = Depends(get_time_window(rounding=10, grace_time=60)),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
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
