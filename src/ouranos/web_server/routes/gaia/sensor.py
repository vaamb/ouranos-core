import typing as t

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.database.models.gaia import Measure, Sensor
from ouranos.core.utils import timeWindow
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.common_queries import (
    ecosystems_uid_q, sensor_level_q
)


router = APIRouter(
    prefix="/sensor",
    responses={404: {"description": "Not found"}},
    tags=["gaia/sensor"],
)


current_data_query = Query(default=False, description="Fetch the current data")
historic_data_query = Query(default=False, description="Fetch logged data")


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


@router.get("")
async def get_sensors(
        sensors_uid: t.Optional[list[str]] = Query(
            default=None, description="A list of sensor uids"),
        ecosystems_uid: t.Optional[list[str]] = ecosystems_uid_q,
        sensors_level: t.Optional[list[str]] = sensor_level_q,
        sensors_model: t.Optional[list[str]] = Query(
            default=None, description="A list of precise sensor model"),
        measures: t.Optional[list[str]] = Query(
            default=None, description="A list of measures taken"),
        current_data: bool = current_data_query,
        historic_data: bool = historic_data_query,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    sensors = await Sensor.get_multiple(
        session, sensors_uid, ecosystems_uid, sensors_level, sensors_model,
        time_window)
    return [
        await sensor.get_overview(
            session, measures, current_data, historic_data, time_window)
        for sensor in sensors
    ]


@router.get("/measures_available", response_model=list[validate.gaia.measure])
async def get_measures_available(session: AsyncSession = Depends(get_session)):
    measures = await Measure.get_multiple(session)
    return measures


@router.get("/u/{uid}")
async def get_sensor(
        uid: str = Query(description="A sensor uid"),
        current_data: bool = current_data_query,
        historic_data: bool = historic_data_query,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await sensor_or_abort(session, uid)
    response = await sensor.get_overview(
        session, None, current_data, historic_data, time_window)
    return response


@router.get("/u/{uid}/data/current")
async def get_sensor_current_data(
        uid: str = Query(description="A sensor uid"),
        measures: t.Optional[list[str]] = Query(
            default=None, description="A list of measures taken by the sensor"),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await sensor_or_abort(session, uid)
    if not measures:
        measures = [m.name for m in sensor.measures]
    return [
        {
            "measure": measure,
            "value": await sensor.get_recent_timed_values(session, measure),
        }
        for measure in measures
    ]


@router.get("/u/{uid}/data/historic")
async def get_sensor_historic_data(
        uid: str = Query(description="A sensor uid"),
        measures: t.Optional[list[str]] = Query(
            default=None, description="A list of measures taken by the sensor"),
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await sensor_or_abort(session, uid)
    if not measures:
        measures = [m.name for m in sensor.measures]
    return [
        {
            "measure": measure,
            "span": (time_window.start, time_window.end),
            "values": await sensor.get_historic_timed_values(session, measure, time_window),
        }
        for measure in measures
    ]
