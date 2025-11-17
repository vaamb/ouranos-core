from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from datetime import timedelta
from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, status)
import humanize
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher
import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.database.models.gaia import (
    Ecosystem, EnvironmentParameter, NycthemeralCycle, WeatherEvent)
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.core.utils import timeWindow
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.gaia.utils import (
    ecosystem_or_abort, eids_desc, emit_crud_event, euid_desc, in_config_desc)
from ouranos.web_server.validate.gaia.ecosystem import (
    EcosystemCreationPayload, EcosystemBaseInfoUpdatePayload, EcosystemInfo,
    EcosystemManagementUpdatePayload, EcosystemManagementInfo, ManagementInfo,
    EcosystemLightInfo, NycthemeralCycleUpdatePayload,
    EnvironmentParameterCreationPayload, EnvironmentParameterUpdatePayload,
    EnvironmentParameterInfo, EcosystemEnvironmentParametersInfo,
    WeatherEventCreationPayload, WeatherEventUpdatePayload, WeatherEventInfo,
    EcosystemWeatherEventsInfo,
    EcosystemActuatorInfo, EcosystemActuatorRecords, EcosystemTurnActuatorPayload)


router = APIRouter(
    prefix="/ecosystem",
    responses={404: {"description": "Not found"}},
    tags=["gaia/ecosystem"],
)


env_parameter_desc = (
    "The environment parameter targeted. Leave empty to select them all")

weather_param_desc = (
    "The weather parameter targeted. Leave empty to select them all")

HardwareTypeName = StrEnum(
    "HardwareTypeName",
    [i.name for i in gv.HardwareType if i in gv.HardwareType.actuator]
)


async def environment_parameter_or_abort(
        session: AsyncSession,
        ecosystem_uid: str,
        parameter: str,
) -> EnvironmentParameter:
    environment_parameter = await EnvironmentParameter.get(
        session, ecosystem_uid=ecosystem_uid, parameter=parameter)
    if not environment_parameter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No environment parameter found"
        )
    return environment_parameter


async def weather_event_or_abort(
        session: AsyncSession,
        ecosystem_uid: str,
        parameter: str,
) -> WeatherEvent:
    weather_event = await WeatherEvent.get(
        session, ecosystem_uid=ecosystem_uid, parameter=parameter)
    if not weather_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weather event found"
        )
    return weather_event


# ------------------------------------------------------------------------------
#   Base ecosystem info
# ------------------------------------------------------------------------------
@router.get("", response_model=list[EcosystemInfo])
async def get_ecosystems(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    return ecosystems


@router.post("/u",
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_operator)])
async def create_ecosystem(
        payload: Annotated[
            EcosystemCreationPayload,
            Body(description="Information about the new ecosystem"),
        ],
):
    ecosystem_dict = payload.model_dump()
    try:
        # Special case of dispatcher.emit as the ecosystem doesn't exist yet
        dispatcher: AsyncDispatcher = DispatcherFactory.get("application-internal")
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem_dict["engine_uid"],
                ),
                action=gv.CrudAction.create,
                target="ecosystem",
                data=ecosystem_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return (
            f"Request to create the new ecosystem '{ecosystem_dict['name']}' "
            f"successfully sent to engine '{ecosystem_dict['engine_uid']}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send ecosystem creation order to engine for "
                f"ecosystem '{ecosystem_dict['name']}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`"
            ),
        )


@router.get("/u/{ecosystem_id}", response_model=EcosystemInfo)
async def get_ecosystem(
        ecosystem_id: Annotated[
            str,
            Path(description="An ecosystem id, either its uid or its name"),
        ],
        session: Annotated [AsyncSession, Depends(get_session)],
):
    ecosystem = await Ecosystem.get_by_id(session, ecosystem_id=ecosystem_id)
    if ecosystem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No ecosystem(s) found"
        )
    return ecosystem


@router.put("/u/{ecosystem_uid}",
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_ecosystem(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        payload: Annotated[
            EcosystemBaseInfoUpdatePayload,
            Body(description="Updated information about the ecosystem"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    ecosystem_dict = payload.model_dump(exclude_defaults=True)
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.update, "ecosystem",
            {"ecosystem_id": ecosystem.uid, **ecosystem_dict})
        return (
            f"Request to update the ecosystem '{ecosystem.name}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send ecosystem creation order to engine for "
                f"ecosystem '{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )


@router.delete("/u/{ecosystem_uid}",
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_operator)])
async def delete_ecosystem(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.delete, "ecosystem", ecosystem.uid)
        return (
            f"Request to delete the ecosystem '{ecosystem.name}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send delete order order ecosystem with uid "
                f"'{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )


# ------------------------------------------------------------------------------
#   Ecosystem management
#   Rem: there is no 'post' method as management dict is automatically created
#        upon ecosystem creation
# ------------------------------------------------------------------------------
@router.get("/managements_available", response_model=list[ManagementInfo])
async def get_managements_available():
    return [
        {"name": management.name, "value": management.value}
        for management in gv.ManagementFlags
    ]


@router.get("/management", response_model=list[EcosystemManagementInfo])
async def get_ecosystems_management(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        await ecosystem.get_functionalities(session)
        for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{ecosystem_uid}/management",
            response_model=EcosystemManagementInfo)
async def get_ecosystem_management(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    response = await ecosystem.get_functionalities(session)
    return response


@router.put("/u/{ecosystem_uid}/management",
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_ecosystem_management(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        payload: Annotated[
            EcosystemManagementUpdatePayload,
            Body(description="Updated information about the ecosystem management"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    management_dict = payload.model_dump(exclude_defaults=True)
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.update, "management", management_dict)
        return (
            f"Request to update the ecosystem '{ecosystem.name}'\' management "
            f"successfully sent to engine '{ecosystem.engine_uid}'",
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send ecosystem' management update order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


# ------------------------------------------------------------------------------
#   Ecosystem light
#   Rem: there is no 'post' method as light info dict is automatically created
#        upon ecosystem creation
# ------------------------------------------------------------------------------
@router.get("/light", response_model=list[EcosystemLightInfo])
async def get_ecosystems_lighting(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = []
    for ecosystem in ecosystems:
        lighting = await NycthemeralCycle.get(session, ecosystem_uid=ecosystem.uid)
        if lighting is not None:
            response.append(
                {
                    "uid": ecosystem.uid,
                    "name": ecosystem.name,
                    **lighting.to_dict()
                }
            )
    return response


@router.get("/u/{ecosystem_uid}/light", response_model=EcosystemLightInfo)
async def get_ecosystem_lighting(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    lighting = await NycthemeralCycle.get(session, ecosystem_uid=ecosystem.uid)
    if lighting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lighting found for ecosystem with uid '{ecosystem_uid}'"
        )
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        **lighting.to_dict()
    }
    return response


@router.put("/u/{ecosystem_uid}/light",
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_ecosystem_lighting(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        payload: Annotated[
            NycthemeralCycleUpdatePayload,
            Body(description="Updated information about the ecosystem nycthemeral cycle"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    lighting_dict = payload.model_dump(exclude_defaults=True)
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.update, "nycthemeral_config", lighting_dict)
        return (
            f"Request to update the ecosystem '{ecosystem.name}'\' lighting "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send ecosystem' lighting update order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: "
                f"{e}`",
            ),
        )


# ------------------------------------------------------------------------------
#   Ecosystem environment parameters
# ------------------------------------------------------------------------------
@router.get("/environment_parameter",
            response_model=list[EcosystemEnvironmentParametersInfo])
async def get_ecosystems_environment_parameters(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        parameters: Annotated[str | None, Query(description=env_parameter_desc)] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "environment_parameters": await EnvironmentParameter.get_multiple(
            session, ecosystem_uid=[ecosystem.uid, ], parameter=parameters)
        } for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{ecosystem_uid}/environment_parameter",
            response_model=EcosystemEnvironmentParametersInfo)
async def get_ecosystem_environment_parameters(
        *,
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameters: Annotated[str | None, Query(description=env_parameter_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "environment_parameters": await EnvironmentParameter.get_multiple(
            session, ecosystem_uid=[ecosystem.uid, ], parameter=parameters)
    }
    return response


@router.post("/u/{ecosystem_uid}/environment_parameter/u",
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_operator)])
async def create_ecosystem_environment_parameter(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        payload: Annotated[
            EnvironmentParameterCreationPayload,
            Body(description="Creation information about the environment parameters"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    environment_parameter_dict = payload.model_dump()
    parameter = environment_parameter_dict["parameter"]
    try:
        safe_enum_from_name(gv.ClimateParameter, parameter)
        await emit_crud_event(
            ecosystem, gv.CrudAction.create, "environment_parameter",
            environment_parameter_dict)
        return (
            f"Request to create the environment parameter '{parameter}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send environment parameter creation order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/u/{ecosystem_uid}/environment_parameter/u/{parameter}",
            response_model=EnvironmentParameterInfo)
async def get_ecosystem_environment_parameter(
        *,
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameter: Annotated[
            gv.ClimateParameter,
            Path(description="A climate parameter"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    env_parameter = await environment_parameter_or_abort(
        session, ecosystem.uid, parameter)
    return env_parameter


@router.put("/u/{ecosystem_uid}/environment_parameter/u/{parameter}",
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_ecosystem_environment_parameter(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameter: Annotated[
            gv.ClimateParameter,
            Path(description="A climate parameter"),
        ],
        payload: Annotated[
            EnvironmentParameterUpdatePayload,
            Body(description="Updated information about the environment parameters"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    await environment_parameter_or_abort(session, ecosystem.uid, parameter)
    environment_parameter_dict = payload.model_dump(exclude_defaults=True)
    environment_parameter_dict["parameter"] = parameter
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.update, "environment_parameter",
            environment_parameter_dict)
        return (
            f"Request to update the environment parameter '{parameter}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send environment parameter update order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )


@router.delete("/u/{ecosystem_uid}/environment_parameter/u/{parameter}",
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_operator)])
async def delete_ecosystem_environment_parameter(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameter: Annotated[
            gv.ClimateParameter,
            Path(description="A climate parameter"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    await environment_parameter_or_abort(session, ecosystem.uid, parameter)
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.delete, "environment_parameter",
            parameter)
        return (
            f"Request to delete the environment parameter '{parameter}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send environment parameter update order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )


# ------------------------------------------------------------------------------
#   Weather events
# ------------------------------------------------------------------------------
@router.get("/weather_event",
            response_model=list[EcosystemWeatherEventsInfo])
async def get_ecosystems_weather_events(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        parameters: Annotated[
            list[gv.WeatherParameter] | None | None,
            Query(description=weather_param_desc)
        ] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "weather_events": await WeatherEvent.get_multiple(
            session, ecosystem_uid=[ecosystem.uid, ], parameter=parameters)
        } for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{ecosystem_uid}/weather_event",
            response_model=EcosystemWeatherEventsInfo)
async def get_ecosystem_weather_events(
        *,
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameters: Annotated[
            list[gv.WeatherParameter] | None | None,
            Query(description=weather_param_desc)
        ] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "weather_events": await WeatherEvent.get_multiple(
            session, ecosystem_uid=[ecosystem.uid, ], parameter=parameters)
    }
    return response


@router.post("/u/{ecosystem_uid}/weather_event/u",
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_operator)])
async def create_ecosystem_weather_event(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        payload: Annotated[
            WeatherEventCreationPayload,
            Body(description="Creation information about the weather event"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    weather_event_dict = payload.model_dump()
    parameter = weather_event_dict["parameter"]
    try:
        safe_enum_from_name(gv.WeatherParameter, parameter)
        await emit_crud_event(
            ecosystem, gv.CrudAction.create, "weather_event",
            weather_event_dict)
        return (
            f"Request to create the weather event '{parameter}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send weather event creation order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/u/{ecosystem_uid}/weather_event/u/{parameter}",
            response_model=WeatherEventInfo)
async def get_ecosystem_weather_event(
        *,
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameter: Annotated[
            gv.WeatherParameter,
            Path(description="A weather parameter"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    weather_event = await weather_event_or_abort(
        session, ecosystem.uid, parameter)
    return weather_event


@router.put("/u/{ecosystem_uid}/weather_event/u/{parameter}",
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_ecosystem_weather_event(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameter: Annotated[
            gv.WeatherParameter,
            Path(description="A weather parameter"),
        ],
        payload: Annotated[
            WeatherEventUpdatePayload,
            Body(description="Updated information about the weather parameters"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    await weather_event_or_abort(session, ecosystem.uid, parameter)
    weather_event_dict = payload.model_dump(exclude_defaults=True)
    weather_event_dict["parameter"] = parameter
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.update, "weather_event",
            weather_event_dict)
        return (
            f"Request to update the weather parameter '{parameter}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send environment parameter update order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )


@router.delete("/u/{ecosystem_uid}/weather_event/u/{parameter}",
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_operator)])
async def delete_ecosystem_weather_event(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        parameter: Annotated[
            gv.WeatherParameter,
            Path(description="A climate parameter"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    await weather_event_or_abort(session, ecosystem.uid, parameter)
    try:
        await emit_crud_event(
            ecosystem, gv.CrudAction.delete, "weather_event",
            parameter)
        return (
            f"Request to delete the weather parameter '{parameter}' "
            f"successfully sent to engine '{ecosystem.engine_uid}'"
        )
    except Exception as e:
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send weather parameter update order to engine "
                f"for ecosystem '{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )


# ------------------------------------------------------------------------------
#   Ecosystem actuators state
# ------------------------------------------------------------------------------
@router.get("/actuators_state", response_model=list[EcosystemActuatorInfo])
async def get_ecosystems_actuators_status(
        *,
        ecosystems_id: Annotated[list[str] | None, Query(description=eids_desc)] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "actuators_state": await ecosystem.get_actuators_state(session)
        } for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{ecosystem_uid}/actuators_state",
            response_model=EcosystemActuatorInfo)
async def get_ecosystem_actuators_status(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "actuators_state": await ecosystem.get_actuators_state(session)
    }
    return response


@router.get("/u/{ecosystem_uid}/actuator_records/u/{actuator_type}",
            response_model=EcosystemActuatorRecords)
async def get_ecosystem_actuator_records(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        actuator_type: Annotated[
            HardwareTypeName,
            Path(description="The actuator type to search for"),
        ],
        time_window: Annotated[
            timeWindow,
            Depends(get_time_window(rounding=10, grace_time=60)),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    actuator_type = safe_enum_from_name(gv.HardwareType, actuator_type.name)
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "actuator_type": actuator_type,
        "span": (time_window.start, time_window.end),
        "values": await ecosystem.get_timed_values(
            session, actuator_type, time_window),
        # order is added by the serializer
    }
    return response


@router.put("/u/{ecosystem_uid}/turn_actuator/u/{actuator_type}",
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def turn_actuator(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        actuator_type: Annotated[
            HardwareTypeName,
            Path(description="The actuator type to search for"),
        ],
        payload: Annotated[
            EcosystemTurnActuatorPayload,
            Body(description="Instruction for the actuator"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    actuator_type = safe_enum_from_name(gv.HardwareType, actuator_type.name)
    instruction_dict = payload.model_dump()
    mode: gv.ActuatorModePayload = instruction_dict["mode"]
    countdown = instruction_dict["countdown"]
    try:
        dispatcher: AsyncDispatcher = DispatcherFactory.get("application-internal")
        await ecosystem.turn_actuator(
            dispatcher, actuator_type, mode, countdown)
        if countdown:
            humanized_countdown = humanize.time.precisedelta(
                timedelta(seconds=countdown), minimum_unit="seconds",
                format="%0.0f")
            extra = f" in {humanized_countdown}"
        else:
            extra = ""
        return (
            f"Request to turn {ecosystem.name}'s {actuator_type.name} "
            f"actuator to mode '{mode.name}'{extra} successfully sent."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to request ecosystem ''{ecosystem_uid}' to turn its "
                f"{actuator_type.name} actuator to mode '{mode}'. "
                f"Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )
