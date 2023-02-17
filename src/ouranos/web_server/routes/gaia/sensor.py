import typing as t

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.database.models.gaia import Hardware, HardwareType
from ouranos.sdk import api
from ouranos.sdk.api.utils import timeWindow
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import assert_single_uid


if t.TYPE_CHECKING:
    from ouranos.core.database.models.gaia import Hardware


router = APIRouter(
    prefix="/sensor",
    responses={404: {"description": "Not found"}},
    tags=["sensor"],
)


async def sensor_or_abort(
        session: AsyncSession,
        sensor_uid: str
) -> Hardware:
    hardware = await api.hardware.get(
        session=session, hardware_uid=sensor_uid
    )
    if hardware is None or hardware.type != HardwareType.sensor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sensor(s) found"
        )
    return hardware


@router.get("/sensor")
async def get_sensors(
        sensors_uid: t.Optional[list[str]] = Query(default=None),
        ecosystems_uid: t.Optional[list[str]] = Query(default=None),
        sensors_level: t.Optional[list[str]] = Query(default=None),
        sensors_model: t.Optional[list[str]] = Query(default=None),
        measures: t.Optional[list[str]] = Query(default=None),
        current_data: bool = True,
        historic_data: bool = True,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    sensor_objs = await api.sensor.get_multiple(
        session, sensors_uid, ecosystems_uid, sensors_level, sensors_model,
        time_window
    )
    response = [await api.sensor.get_overview(
        session, sensor_obj, measures, current_data,
        historic_data, time_window
    ) for sensor_obj in sensor_objs]
    return response


@router.get("/sensor/measures_available", response_model=list[validate.gaia.measure])
async def get_measures_available(
        names: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session),
):
    measures = await api.measure.get_multiple(session, names)
    return measures


@router.get("/sensor/u/<uid>")
async def get_sensor(
        uid: str,
        current_data: bool = True,
        historic_data: bool = True,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await sensor_or_abort(session, uid)
    response = await api.sensor.get_overview(
        session, sensor, None, current_data, historic_data, time_window,
    )
    return response


@router.get("/sensor/u/<uid>/<measure>")
async def get_measure_for_sensor(
        uid: str,
        measure: str,
        current_data: bool = True,
        historic_data: bool = True,
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
