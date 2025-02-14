from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import gaia_validators as gv

from ouranos.core.database.models.gaia import Ecosystem, Measure, Sensor
from ouranos.core.utils import timeWindow
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.gaia.utils import (
    ecosystem_or_abort, eids_desc, euid_desc, h_level_desc, in_config_desc)
from ouranos.web_server.validate.gaia.sensor import (
    EcosystemSensorData, SensorMeasureCurrentTimedValue,
    SensorMeasureHistoricTimedValue, SensorSkeletonInfo)


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


@router.get("/sensor/skeleton", response_model=list[SensorSkeletonInfo])
async def get_ecosystems_sensors_skeleton(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        level: Annotated[
            list[gv.HardwareLevel],
            Query(description=h_level_desc)
        ] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        time_window: Annotated[
            timeWindow,
            Depends(get_time_window(rounding=10, grace_time=60)),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        await ecosystem.get_sensors_data_skeleton(
            session, time_window=time_window, level=level)
        for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{ecosystem_uid}/sensor/skeleton",
            response_model=SensorSkeletonInfo)
async def get_ecosystem_sensors_skeleton(
        *,
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        level: Annotated[
            list[gv.HardwareLevel],
            Query(description=h_level_desc),
        ] = None,
        time_window: Annotated[
            timeWindow,
            Depends(get_time_window(rounding=10, grace_time=60)),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    response = await ecosystem.get_sensors_data_skeleton(
        session, time_window=time_window, level=level)
    return response


@router.get("/sensor/data/current", response_model=list[EcosystemSensorData])
async def get_measures_available(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
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


@router.get("/u/{ecosystem_uid}/sensor/data/current",
            response_model=EcosystemSensorData)
async def get_ecosystem_current_data(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "values": await ecosystem.get_current_data(session)
    }
    return response


@router.get("/u/{ecosystem_uid}/sensor/u/{hardware_uid}/data/{measure}/current",
            response_model=SensorMeasureCurrentTimedValue)
async def get_sensor_current_data(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        hardware_uid: Annotated[str, Path(description="The uid of a sensor")],
        measure: Annotated[
            str,
            Path(description="The measure for which to fetch current data"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    await ecosystem_or_abort(session, ecosystem_uid)
    sensor = await sensor_or_abort(session, hardware_uid)
    if sensor.type == gv.HardwareType.camera:
        raise HTTPException(
            status_code=status.HTT,
            detail="No current measure available for this kind of sensor"
        )
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


@router.get("/u/{ecosystem_uid}/sensor/u/{hardware_uid}/data/{measure}/historic",
            response_model=SensorMeasureHistoricTimedValue)
async def get_sensor_historic_data(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        hardware_uid: Annotated[str, Path(description="The uid of a sensor")],
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
    await ecosystem_or_abort(session, ecosystem_uid)
    sensor = await sensor_or_abort(session, hardware_uid)
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
