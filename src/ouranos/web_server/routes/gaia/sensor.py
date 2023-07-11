from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import HardwareLevel

from ouranos.core.database.models.gaia import Measure, Sensor
from ouranos.core.utils import timeWindow
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.gaia.utils import (
    ecosystems_uid_q, hardware_level_q)
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.validate.response.gaia import (
    MeasureInfo, SensorCurrentTimedValue, SensorHistoricTimedValue,
    SensorOverview)


router = APIRouter(
    prefix="/sensor",
    responses={404: {"description": "Not found"}},
    tags=["gaia/sensor"],
)


uid_param = Path(description="The uid of a sensor")

current_data_query = Query(default=False, description="Fetch the current data")

historic_data_query = Query(default=False, description="Fetch logged data")

in_use_query = Query(
    default=None, description="Only select sensors that are present (True) "
                              "or have been removed (False) from the current "
                              "gaia ecosystems config")


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


@router.get("", response_model=list[SensorOverview])
async def get_sensors(
        sensors_uid: list[str] | None = Query(
            default=None, description="A list of sensor uids"),
        ecosystems_uid: list[str] | None = ecosystems_uid_q,
        sensors_level: list[HardwareLevel] | None = hardware_level_q,
        sensors_model: list[str] | None = Query(
            default=None, description="A list of precise sensor model"),
        measures: list[str] | None = Query(
            default=None, description="A list of measures taken"),
        current_data: bool = current_data_query,
        historic_data: bool = historic_data_query,
        time_window: timeWindow = Depends(get_time_window),
        in_use: bool | None = in_use_query,
        session: AsyncSession = Depends(get_session),
):
    sensors = await Sensor.get_multiple(
        session=session, hardware_uids=sensors_uid,
        ecosystem_uids=ecosystems_uid, levels=sensors_level, 
        models=sensors_model, time_window=time_window, in_use=in_use)
    return [
        await sensor.get_overview(
            session, measures, current_data, historic_data, time_window)
        for sensor in sensors
    ]


@router.get("/measures_available", response_model=list[MeasureInfo])
async def get_measures_available(session: AsyncSession = Depends(get_session)):
    measures = await Measure.get_multiple(session)
    return measures


@router.get("/u/{uid}", response_model=SensorOverview)
async def get_sensor(
        uid: str = uid_param,
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


@router.get("/u/{uid}/data/current", response_model=list[SensorCurrentTimedValue])
async def get_sensor_current_data(
        uid: str = uid_param,
        measures: list[str] | None = Query(
            default=None, description="A list of measures taken by the sensor"),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await sensor_or_abort(session, uid)
    if not measures:
        measures = [m.name for m in sensor.measures]
    response = await sensor.get_current_data(session, measures)
    return response


@router.get("/u/{uid}/data/historic", response_model=list[SensorHistoricTimedValue])
async def get_sensor_historic_data(
        uid: str = uid_param,
        measures: list[str] | None = Query(
            default=None, description="A list of measures taken by the sensor"),
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await sensor_or_abort(session, uid)
    if not measures:
        measures = [m.name for m in sensor.measures]
    response = await sensor.get_historic_data(session, measures, time_window)
    return response
