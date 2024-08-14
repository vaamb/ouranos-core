from __future__ import annotations

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, Response, status)
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher
import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.database.models.gaia import (
    Ecosystem, EnvironmentParameter, Lighting)
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.core.utils import timeWindow
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.utils import (
    ecosystem_or_abort, ecosystems_uid_q, hardware_level_q)
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.gaia.ecosystem import (
    EcosystemCreationPayload, EcosystemUpdatePayload, EcosystemInfo,
    EcosystemManagementUpdatePayload, EcosystemManagementInfo, ManagementInfo,
    EcosystemLightMethodUpdatePayload, EcosystemLightInfo,
    EnvironmentParameterCreationPayload, EnvironmentParameterUpdatePayload,
    EnvironmentParameterInfo,
    EcosystemActuatorInfo, EcosystemActuatorRecords, EcosystemTurnActuatorPayload)
from ouranos.web_server.validate.gaia.hardware import HardwareInfo
from ouranos.web_server.validate.gaia.sensor import (
    EcosystemSensorData, SensorSkeletonInfo)


dispatcher: AsyncDispatcher = DispatcherFactory.get("application-internal")


router = APIRouter(
    prefix="/ecosystem",
    responses={404: {"description": "Not found"}},
    tags=["gaia/ecosystem"],
)


id_param_query = Path(description="An ecosystem id, either its uid or its name")

in_config_query = Query(
    default=None, description="Only select ecosystems that are present (True) "
                              "or also include the ones that have been removed "
                              "(False) from the current gaia ecosystems config "
                              "files")

in_config_query_hardware = Query(
    default=None, description="Only select hardware that are present (True) "
                              "or also include the ones that have been removed "
                              "(False) from the current gaia ecosystems config "
                              "files")

env_parameter_query = Query(
    default=None, description="The environment parameter targeted. Leave empty "
                              "to select them all")


async def environment_parameter_or_abort(
        session: AsyncSession,
        ecosystem_uid: str,
        parameter: str
) -> None:
    environment_parameter = await EnvironmentParameter.get(
        session=session, uid=ecosystem_uid, parameter=parameter)
    if not environment_parameter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No environment_parameter found"
        )


# ------------------------------------------------------------------------------
#   Base ecosystem info
# ------------------------------------------------------------------------------
@router.get("", response_model=list[EcosystemInfo])
async def get_ecosystems(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session),
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    return ecosystems


@router.post("/u",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_operator)])
async def create_ecosystem(
        response: Response,
        payload: EcosystemCreationPayload = Body(
            description="Information about the new ecosystem"),
):
    ecosystem_dict = payload.model_dump()
    try:
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
        return ResultResponse(
            msg=f"Request to create the new ecosystem '{ecosystem_dict['name']}' "
                f"successfully sent to engine '{ecosystem_dict['engine_uid']}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send ecosystem creation order to engine for "
                f"ecosystem '{ecosystem_dict['name']}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/u/{id}", response_model=EcosystemInfo)
async def get_ecosystem(
        id: str = id_param_query,
        session: AsyncSession = Depends(get_session)
):
    ecosystem = await ecosystem_or_abort(session, id)
    return ecosystem


@router.put("/u/{id}",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse,
            dependencies=[Depends(is_operator)])
async def update_ecosystem(
        response: Response,
        id: str = id_param_query,
        payload: EcosystemUpdatePayload = Body(
            description="Updated information about the ecosystem"),
        session: AsyncSession = Depends(get_session)
):
    ecosystem_dict = payload.model_dump()
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.update,
                target="ecosystem",
                data=ecosystem_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to update the ecosystem '{ecosystem.name}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send ecosystem update order to engine "
                f"for ecosystem '{id}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.delete("/u/{id}",
               response_model=ResultResponse,
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_operator)])
async def delete_ecosystem(
        response: Response,
        id: str = id_param_query,
        session: AsyncSession = Depends(get_session)
):
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid,
                ),
                action=gv.CrudAction.delete,
                target="ecosystem",
                data=ecosystem.uid,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to delete the ecosystem '{ecosystem.name}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send delete order for ecosystem with id '{id}'. "
                f"Error msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
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
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session),
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        await ecosystem.get_functionalities(session)
        for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{id}/management", response_model=EcosystemManagementInfo)
async def get_ecosystem_management(
        id: str = id_param_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await ecosystem.get_functionalities(session)
    return response


@router.put("/u/{id}/management",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse,
            dependencies=[Depends(is_operator)])
async def update_management(
        response: Response,
        id: str = id_param_query,
        payload: EcosystemManagementUpdatePayload = Body(
            description="Updated information about the ecosystem management"),
        session: AsyncSession = Depends(get_session)
):
    management_dict = payload.model_dump()
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.update,
                target="management",
                data=management_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to update the ecosystem '{ecosystem.name}'\' management "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send ecosystem' management update order to engine "
                f"for ecosystem '{id}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


# ------------------------------------------------------------------------------
#   Ecosystem sensors skeleton
# ------------------------------------------------------------------------------
@router.get("/sensors_skeleton", response_model=list[SensorSkeletonInfo])
async def get_ecosystems_sensors_skeleton(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        level: list[gv.HardwareLevel] | None = hardware_level_q,
        time_window: timeWindow = Depends(get_time_window(rounding=10, grace_time=60)),
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session),
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        await ecosystem.get_sensors_data_skeleton(
            session, time_window=time_window, level=level)
        for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{id}/sensors_skeleton", response_model=SensorSkeletonInfo)
async def get_ecosystem_sensors_skeleton(
        id: str = id_param_query,
        level: list[gv.HardwareLevel] | None = hardware_level_q,
        time_window: timeWindow = Depends(get_time_window(rounding=10, grace_time=60)),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await ecosystem.get_sensors_data_skeleton(
        session, time_window=time_window, level=level)
    return response


# ------------------------------------------------------------------------------
#   Ecosystem light
#   Rem: there is no 'post' method as light info dict is automatically created
#        upon ecosystem creation
# ------------------------------------------------------------------------------
@router.get("/light", response_model=list[EcosystemLightInfo])
async def get_ecosystems_light(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session),
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = []
    for ecosystem in ecosystems:
        lighting = await Lighting.get(session, ecosystem.uid)
        if lighting is not None:
            response.append(
                {
                    "uid": ecosystem.uid,
                    "name": ecosystem.name,
                    **lighting.to_dict()
                }
            )
    return response


@router.get("/u/{id}/light", response_model=EcosystemLightInfo)
async def get_ecosystem_lighting(
        id: str = id_param_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    lighting = await Lighting.get(session, ecosystem.uid)
    if lighting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lighting found for ecosystem with id '{id}'"
        )
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        **lighting.to_dict()
    }
    return response


@router.put("/u/{id}/light",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse,
            dependencies=[Depends(is_operator)])
async def update_ecosystem_lighting(
        response: Response,
        id: str = id_param_query,
        payload: EcosystemLightMethodUpdatePayload = Body(
            description="Updated information about the ecosystem management"),
        session: AsyncSession = Depends(get_session)
):
    lighting_dict = payload.model_dump()
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    try:
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.update,
                target="lighting",
                data=lighting_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to update the ecosystem '{ecosystem.name}'\' lighting "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send ecosystem' lighting update order to engine "
                f"for ecosystem '{id}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


# ------------------------------------------------------------------------------
#   Ecosystem environment parameters
# ------------------------------------------------------------------------------
@router.get("/environment_parameters", response_model=list[EnvironmentParameterInfo])
async def get_ecosystems_environment_parameters(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        parameters: list[str] | None = env_parameter_query,
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await Ecosystem.get_multiple_by_id(
        session, ecosystems_id=ecosystems_id, in_config=in_config)
    response = [
        {
            "uid": ecosystem.uid,
            "name": ecosystem.name,
            "environment_parameters": await EnvironmentParameter.get_multiple(
                session, [ecosystem.uid, ], parameters)
        } for ecosystem in ecosystems
    ]
    return response


@router.post("/u/{id}/environment_parameters",
             status_code=status.HTTP_202_ACCEPTED,
             response_model=ResultResponse,
             dependencies=[Depends(is_operator)])
async def create_environment_parameters(
        response: Response,
        id: str = id_param_query,
        payload: EnvironmentParameterCreationPayload = Body(
            description="Creation information about the environment parameters"),
        session: AsyncSession = Depends(get_session)
):
    environment_parameter_dict = payload.model_dump()
    parameter = environment_parameter_dict["parameter"]
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        safe_enum_from_name(gv.ClimateParameter, parameter)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.create,
                target="environment_parameter",
                data=environment_parameter_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to create the environment parameter '{parameter}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send environment parameter creation order to engine "
                f"for ecosystem '{id}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/u/{id}/environment_parameters", response_model=EnvironmentParameterInfo)
async def get_ecosystem_environment_parameters(
        id: str = id_param_query,
        parameters: list[str] | None = env_parameter_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "environment_parameters": await EnvironmentParameter.get_multiple(
            session, [ecosystem.uid, ], parameters)
    }
    return response


@router.put("/u/{id}/environment_parameters/{parameter}",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse,
            dependencies=[Depends(is_operator)])
async def update_environment_parameters(
        response: Response,
        id: str = id_param_query,
        parameter: str = Path(description="A climate parameter"),
        payload: EnvironmentParameterUpdatePayload = Body(
            description="Updated information about the environment parameters"),
        session: AsyncSession = Depends(get_session)
):
    environment_parameter_dict = payload.model_dump()
    environment_parameter_dict["parameter"] = parameter
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await environment_parameter_or_abort(session, id, parameter)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.update,
                target="environment_parameter",
                data=environment_parameter_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to update the environment parameter '{parameter}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send environment parameter update order to engine "
                f"for ecosystem '{id}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.delete("/u/{id}/environment_parameters/{parameter}",
               status_code=status.HTTP_202_ACCEPTED,
               response_model=ResultResponse,
               dependencies=[Depends(is_operator)])
async def delete_environment_parameters(
        response: Response,
        id: str = id_param_query,
        parameter: str = Path(description="A climate parameter"),
        session: AsyncSession = Depends(get_session)
):
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await environment_parameter_or_abort(session, id, parameter)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.delete,
                target="environment_parameter",
                data=parameter
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to delete the environment parameter '{parameter}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send environment parameter update order to engine "
                f"for ecosystem '{id}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


# ------------------------------------------------------------------------------
#   Ecosystem hardware
#   Rem: there is no 'put' method as hardware has its own API interface
# ------------------------------------------------------------------------------
@router.post("/u/{id}/hardware",
             status_code=status.HTTP_202_ACCEPTED,
             response_model=ResultResponse,
             dependencies=[Depends(is_operator)])
async def create_ecosystem_hardware(
        response: Response,
        id: str = id_param_query,
        payload: gv.AnonymousHardwareConfig = Body(
            description="Information about the new hardware"),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    hardware_dict = payload.model_dump()
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.create,
                target="hardware",
                data=hardware_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to create the new hardware '{hardware_dict['name']}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send hardware creation order to engine for "
                f"ecosystem '{id}'. Error msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/u/{id}/hardware", response_model=list[HardwareInfo])
async def get_ecosystem_hardware(
        id: str = id_param_query,
        hardware_type: list[gv.HardwareType] | None = Query(
            default=None, description="A list of types of hardware"),
        in_config: bool | None = in_config_query_hardware,
        session: AsyncSession = Depends(get_session),
):
    ecosystem = await ecosystem_or_abort(session, id)
    hardware = await ecosystem.get_hardware(
        session, hardware_type=hardware_type, in_config=in_config)
    return hardware


# ------------------------------------------------------------------------------
#   Ecosystem current data
# ------------------------------------------------------------------------------
@router.get("/current_data", response_model=list[EcosystemSensorData])
async def get_ecosystems_current_data(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session),
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


@router.get("/u/{id}/current_data", response_model=EcosystemSensorData)
async def get_ecosystem_current_data(
        id: str = id_param_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "values": await ecosystem.get_current_data(session)
    }
    return response


# ------------------------------------------------------------------------------
#   Ecosystem actuators state
# ------------------------------------------------------------------------------
@router.get("/actuators_state", response_model=list[EcosystemActuatorInfo])
async def get_ecosystems_actuators_status(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session),
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


@router.get("/u/{id}/actuators_state", response_model=EcosystemActuatorInfo)
async def get_ecosystem_actuators_status(
        id: str = id_param_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = {
        "uid": ecosystem.uid,
        "name": ecosystem.name,
        "actuators_state": await ecosystem.get_actuators_state(session)
    }
    return response


@router.get("/u/{id}/actuator_records/{actuator_type}",
            response_model=EcosystemActuatorRecords)
async def get_ecosystem_actuator_records(
        id: str = id_param_query,
        actuator_type: str = Path(description="The actuator type to search for."),
        time_window: timeWindow = Depends(get_time_window(rounding=1, grace_time=10)),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    assert_single_uid(actuator_type, "actuator_type")
    error = False
    try:
        actuator_type = safe_enum_from_name(gv.HardwareType, actuator_type)
    except ValueError:
        error = True
    else:
        if not actuator_type & gv.HardwareType.actuator:
            error = True
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid actuator type"
        )
    ecosystem = await ecosystem_or_abort(session, id)
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


@router.put("/u/{id}/turn_actuator",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def turn_actuator(
        id: str = id_param_query,
        payload: EcosystemTurnActuatorPayload = Body(
            description="Instruction for the actuator"),
        session: AsyncSession = Depends(get_session)
):
    instruction_dict = payload.model_dump()
    actuator: gv.HardwareType = instruction_dict["actuator"]
    if not actuator & gv.HardwareType.actuator:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{actuator.name.capitalize()} is not an actuator"
        )
    mode: gv.ActuatorModePayload = instruction_dict["mode"]
    countdown = instruction_dict["countdown"]
    try:
        assert_single_uid(id)
        ecosystem = await ecosystem_or_abort(session, id)
        await ecosystem.turn_actuator(
            dispatcher, actuator, mode, countdown)
        return ResultResponse(
            msg=f"Turned {ecosystem.name}'s {actuator.name} to mode '{mode.name}'",
            status=ResultStatus.success
        )
    except Exception as e:
        return ResultResponse(
            msg=f"Failed to turn {actuator} from ecosystem with id {id} to "
                f"mode '{mode}'. Error msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )
