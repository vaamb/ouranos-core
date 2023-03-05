import typing as t

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.database.models.gaia import Hardware, HardwareType
from ouranos.sdk import api
from ouranos.sdk.api.utils import timeWindow
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.common_queries import (
    ecosystems_uid_q, sensor_level_q
)


if t.TYPE_CHECKING:
    from ouranos.core.database.models.gaia import Hardware


router = APIRouter(
    prefix="/sensor",
    responses={404: {"description": "Not found"}},
    tags=["gaia/sensor"],
)


current_data_query = Query(default=True, description="Fetch the current data")
historic_data_query = Query(default=True, description="Fetch logged data")


async def sensor_or_abort(
        session: AsyncSession,
        sensor_uid: str
) -> Hardware:
    hardware = await api.hardware.get(
        session=session, hardware_uid=sensor_uid)
    if hardware is None or hardware.type != HardwareType.sensor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sensor(s) found"
        )
    return hardware


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
    sensor_objs = await api.sensor.get_multiple(
        session, sensors_uid, ecosystems_uid, sensors_level, sensors_model,
        time_window)
    response = [await api.sensor.get_overview(
        session, sensor_obj, measures, current_data,
        historic_data, time_window
    ) for sensor_obj in sensor_objs]
    return response


@router.get("/sensor/measures_available", response_model=list[validate.gaia.measure])
async def get_measures_available(session: AsyncSession = Depends(get_session)):
    measures = await api.measure.get_multiple(session)
    return measures


@router.get("/sensor/u/{uid}")
async def get_sensor(
        uid: str = Query(description="A sensor uid"),
        current_data: bool = current_data_query,
        historic_data: bool = historic_data_query,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await sensor_or_abort(session, uid)
    response = await api.sensor.get_overview(
        session, sensor, None, current_data, historic_data, time_window)
    return response


@router.get("/sensor/u/{uid}/{measure}")
async def get_measure_for_sensor(
        uid: str = Query(description="A sensor uid"),
        measure: str = Query(description="The name of the measure to fetch"),
        current_data: bool = current_data_query,
        historic_data: bool = historic_data_query,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    assert_single_uid(measure, "measure")
    sensor = await sensor_or_abort(session, uid)
    response = {}
    if measure in [m.name for m in sensor.measures]:
        response = await api.sensor.get_overview(
            session, sensor, measure, current_data, historic_data,
            time_window
        )
    return response
