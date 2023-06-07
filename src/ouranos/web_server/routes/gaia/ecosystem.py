from __future__ import annotations

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, Response, status)
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import HardwareLevel, ManagementFlags

from ouranos.core.database.models import Ecosystem, EnvironmentParameter, Light
from ouranos.core.utils import DispatcherFactory, timeWindow
from ouranos.core.validate.payload import ActuatorTurnToPayload
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session, get_time_window
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.common_queries import (
    ecosystems_uid_q, hardware_level_q)
from ouranos.web_server.validate.payload.gaia import (
    EcosystemCreationPayload, EcosystemManagementUpdatePayload,
    EcosystemUpdatePayload, EnvironmentParameterCreationPayload,
    EnvironmentParameterUpdatePayload)
from ouranos.web_server.validate.response.base import (
    ResultResponse, ResultStatus)
from ouranos.web_server.validate.response.gaia import (
    EcosystemInfo, EcosystemLightInfo, EcosystemManagementInfo,
    EnvironmentParameterInfo, ManagementInfo, EcosystemSensorData,
    SensorSkeletonInfo)


router = APIRouter(
    prefix="/ecosystem",
    responses={404: {"description": "Not found"}},
    tags=["gaia/ecosystem"],
)


id_param = Path(description="An ecosystem id, either its uid or its name")

env_parameter_query = Query(
    default=None, description="The environment parameter targeted. Leave empty "
                              "to select them all")


async def ecosystem_or_abort(
        session: AsyncSession,
        ecosystem_id: str,
) -> Ecosystem:
    ecosystem = await Ecosystem.get(session=session, ecosystem_id=ecosystem_id)
    if ecosystem:
        return ecosystem
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


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


@router.get("", response_model=list[EcosystemInfo])
async def get_ecosystems(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session),
):
    ecosystems = await Ecosystem.get_multiple(
        session=session, ecosystems=ecosystems_id)
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
    ecosystem_dict = payload.dict()
    try:
        # TODO: dispatch to Gaia
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
        id: str = id_param,
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
        id: str = id_param,
        payload: EcosystemUpdatePayload = Body(
            description="Updated information about the ecosystem"),
        session: AsyncSession = Depends(get_session)
):
    ecosystem_dict = payload.dict()
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        # TODO: dispatch to Gaia
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
        id: str = id_param,
        session: AsyncSession = Depends(get_session)
):
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        # TODO: dispatch to Gaia
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


@router.get("/managements_available", response_model=list[ManagementInfo])
async def get_managements_available():
    return [
        {"name": management.name, "value": management.value}
        for management in ManagementFlags
    ]


@router.get("/management", response_model=list[EcosystemManagementInfo])
async def get_ecosystems_management(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await Ecosystem.get_multiple(session, ecosystems_id)
    response = [
        await ecosystem.functionalities(session)
        for ecosystem in ecosystems
    ]
    return response


# TODO: use functionality
@router.get("/u/{id}/management", response_model=EcosystemManagementInfo)
async def get_ecosystem_management(
        id: str = id_param,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await ecosystem.functionalities(session)
    return response


@router.put("/u/{id}/management",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse,
            dependencies=[Depends(is_operator)])
async def update_management(
        response: Response,
        id: str = id_param,
        payload: EcosystemManagementUpdatePayload = Body(
            description="Updated information about the ecosystem management"),
        session: AsyncSession = Depends(get_session)
):
    management_dict = payload.dict()
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        # TODO: dispatch to Gaia
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


@router.get("/sensors_skeleton", response_model=list[SensorSkeletonInfo])
async def get_ecosystems_sensors_skeleton(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        level: list[HardwareLevel] | None = hardware_level_q,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await Ecosystem.get_multiple(session, ecosystems_id)
    response = [
        await ecosystem.sensors_data_skeleton(session, time_window, level)
        for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{id}/sensors_skeleton", response_model=SensorSkeletonInfo)
async def get_ecosystem_sensors_skeleton(
        id: str = id_param,
        level: list[HardwareLevel] | None = hardware_level_q,
        time_window: timeWindow = Depends(get_time_window),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await ecosystem.sensors_data_skeleton(
        session, time_window, level
    )
    return response


@router.get("/light", response_model=list[EcosystemLightInfo])
async def get_ecosystems_light(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session)
):
    response = await Light.get_multiple(session, ecosystems_id)
    return response


@router.get("/u/{id}/light", response_model=EcosystemLightInfo)
async def get_ecosystem_light(
        id: str = id_param,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await Light.get(session, ecosystem.uid)
    return response


@router.get("/environment_parameters", response_model=list[EnvironmentParameterInfo])
async def get_ecosystems_environment_parameters(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        parameters: list[str] | None = env_parameter_query,
        session: AsyncSession = Depends(get_session)
):
    response = await EnvironmentParameter.get_multiple(
        session, ecosystems_id, parameters)
    return response


@router.post("/u/{id}/environment_parameters",
             status_code=status.HTTP_202_ACCEPTED,
             response_model=ResultResponse,
             dependencies=[Depends(is_operator)])
async def create_environment_parameters(
        response: Response,
        id: str = id_param,
        payload: EnvironmentParameterCreationPayload = Body(
            description="Creation information about the environment parameters"),
        session: AsyncSession = Depends(get_session)
):
    environment_parameter_dict = payload.dict()
    parameter = environment_parameter_dict["parameter"]
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await environment_parameter_or_abort(session, id, parameter)
        # TODO: dispatch to Gaia
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


@router.get("/u/{id}/environment_parameters", response_model=list[EnvironmentParameterInfo])
async def get_ecosystem_environment_parameters(
        id: str = id_param,
        parameters: list[str] | None = env_parameter_query,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = await EnvironmentParameter.get_multiple(
        session, [ecosystem.uid, ], parameters)
    return response


@router.put("/u/{id}/environment_parameters",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse,
            dependencies=[Depends(is_operator)])
async def update_environment_parameters(
        response: Response,
        id: str = id_param,
        payload: EnvironmentParameterUpdatePayload = Body(
            description="Updated information about the environment parameters"),
        session: AsyncSession = Depends(get_session)
):
    environment_parameter_dict = payload.dict()
    parameter = environment_parameter_dict["parameter"]
    try:
        ecosystem = await ecosystem_or_abort(session, id)
        await environment_parameter_or_abort(session, id, parameter)
        # TODO: dispatch to Gaia
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


@router.get("/current_data", response_model=list[EcosystemSensorData])
async def get_ecosystems_current_data(
        ecosystems_id: list[str] | None = ecosystems_uid_q,
        session: AsyncSession = Depends(get_session)
):
    ecosystems = await Ecosystem.get_multiple(
        session=session, ecosystems=ecosystems_id)
    response = [
        {
            "ecosystem_uid": ecosystem.uid,
            "data": await ecosystem.current_data(session)
        } for ecosystem in ecosystems
    ]
    return response


@router.get("/u/{id}/current_data", response_model=EcosystemSensorData)
async def get_ecosystem_current_data(
        id: str = id_param,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(id)
    ecosystem = await ecosystem_or_abort(session, id)
    response = {
        "ecosystem_uid": ecosystem.uid,
        "data": await ecosystem.current_data(session)
    }
    return response


@router.put("/u/{id}/turn_actuator",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def turn_actuator(
        id: str = id_param,
        payload: ActuatorTurnToPayload = Body(
            description="Instruction for the actuator"),
        session: AsyncSession = Depends(get_session)
):
    instruction_dict = payload.dict()
    actuator = instruction_dict["actuator"]
    mode = instruction_dict["mode"]
    countdown = instruction_dict["countdown"]
    try:
        assert_single_uid(id)
        ecosystem = await ecosystem_or_abort(session, id)
        dispatcher = DispatcherFactory.get("application")
        await ecosystem.turn_actuator(
            dispatcher, actuator, mode, countdown)
        return ResultResponse(
            msg=f"Turned {ecosystem.name}'s {actuator} to mode '{mode}'",
            status=ResultStatus.success
        )
    except Exception as e:
        return ResultResponse(
            msg=f"Failed to turn {actuator} from ecosystem with id {id} to "
                f"mode '{mode}'. Error msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )
