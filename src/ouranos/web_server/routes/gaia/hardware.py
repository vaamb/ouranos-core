import typing as t

from fastapi import Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import router
from ..utils import assert_single_uid
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos import sdk
from ouranos.sdk.api.utils import timeWindow


if t.TYPE_CHECKING:
    from ouranos.core.database.models.gaia import Hardware


async def hardware_or_abort(
        session: AsyncSession,
        hardware_uid: str
) -> "Hardware":
    hardware = await sdk.hardware.get(
        session=session, hardware_uid=hardware_uid
    )
    if hardware:
        return hardware
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("/hardware")
async def get_multiple_hardware(
        hardware_uid: t.Optional[list[str]] = Query(default=None),
        ecosystems_uid: t.Optional[list[str]] = Query(default=None),
        hardware_level: t.Optional[list[str]] = Query(default=None),
        hardware_type: t.Optional[list[str]] = Query(default=None),
        hardware_model: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session),
):
    hardware = await sdk.hardware.get_multiple(
        session, hardware_uid, ecosystems_uid, hardware_level,
        hardware_type, hardware_model
    )
    response = [sdk.hardware.get_info(session, h) for h in hardware]
    return response


@router.get("/hardware/models_available")
async def get_hardware_available():
    response = sdk.hardware.get_models_available()
    return response


@router.post("/hardware/u", dependencies=[Depends(is_operator)])
async def create_hardware(hardware_dict: dict = Depends(Body)):
    try:
        uid = "truc"
        return {"msg": f"New hardware with uid '{uid}' created"}
    except KeyError:
        return {"msg": "The server could not parse the data"}, 500


@router.get("/hardware/u/<uid>")
async def get_hardware(
        uid: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    hardware = await hardware_or_abort(session, uid)
    response = sdk.hardware.get_info(session, hardware)
    return response


@router.put("/hardware/u/<uid>", dependencies=[Depends(is_operator)])
async def update_hardware():
    pass


@router.delete("/hardware/u/<uid>", dependencies=[Depends(is_operator)])
async def delete_hardware():
    pass


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
    sensors = await sdk.sensor.get_multiple(
        session, sensors_uid, ecosystems_uid, sensors_level, sensors_model,
        time_window
    )
    response = [await sdk.sensor.get_overview(
        session, sensor, measures, current_data,
        historic_data, time_window
    ) for sensor in sensors]
    return response


@router.get("/sensor/measures_available")
async def get_measures_available(session: AsyncSession = Depends(get_session)):
    measures = await sdk.measure.get_multiple(session)
    return [sdk.measure.get_info(session, measure) for measure in measures]


@router.get("/sensor/u/<uid>")
async def get_sensor(
        uid: str,
        current_data: bool = True,
        historic_data: bool = True,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session),
):
    assert_single_uid(uid)
    sensor = await hardware_or_abort(session, uid)
    response = await sdk.sensor.get_overview(
        session, sensor, "all", current_data, historic_data, time_window,
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
    sensor = await hardware_or_abort(session, uid)
    response = {}
    if measure in [m.name for m in sensor.measure]:
        response = await sdk.sensor.get_overview(
            session, sensor, measure, current_data, historic_data,
            time_window
        )
    return response
