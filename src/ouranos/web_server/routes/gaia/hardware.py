from __future__ import annotations

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, Response, status)
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher
import gaia_validators as gv

from ouranos.core.database.models.gaia import Ecosystem, Hardware
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.utils import (
    ecosystem_or_abort, ecosystems_uid_q, hardware_level_q)
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.gaia.hardware import (
    HardwareType, HardwareCreationPayload, HardwareInfo, HardwareModelInfo,
    HardwareUpdatePayload)


dispatcher: AsyncDispatcher = DispatcherFactory.get("application-internal")


router = APIRouter(
    prefix="/hardware",
    responses={404: {"description": "Not found"}},
    tags=["gaia/hardware"],
)


uid_param = Path(description="The uid of a hardware")

in_config_query = Query(
    default=None, description="Only select hardware that are present (True) "
                              "or have been removed (False) from the current "
                              "gaia ecosystems config")


async def hardware_or_abort(
        session: AsyncSession,
        hardware_uid: str
) -> Hardware:
    hardware = await Hardware.get(session, uid=hardware_uid)
    if hardware:
        return hardware
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No hardware found"
    )


@router.get("", response_model=list[HardwareInfo])
async def get_multiple_hardware(
        hardware_uid: list[str] | None = Query(
            default=None, description="A list of hardware uids"),
        ecosystems_uid: list[str] | None = ecosystems_uid_q,
        hardware_level: list[gv.HardwareLevel] | None = hardware_level_q,
        hardware_type: list[gv.HardwareType] | None = Query(
            default=None, description="A list of types of hardware"),
        hardware_model: list[str] | None = Query(
            default=None, description="A list of precise hardware model"),
        in_config: bool | None = in_config_query,
        session: AsyncSession = Depends(get_session),
):
    hardware = await Hardware.get_multiple(
        session, hardware_uids=hardware_uid,
        ecosystem_uids=ecosystems_uid, levels=hardware_level,
        types=hardware_type, models=hardware_model, in_config=in_config)
    return hardware


@router.get("/types_available", response_model=list[HardwareType])
async def get_hardware_types_available():
    response = [
        {
            "name": hardware_type.name,
            "value": hardware_type.value
        }
        for hardware_type in gv.HardwareType.__members__.values()
    ]
    return response


@router.get("/models_available", response_model=list[HardwareModelInfo])
async def get_hardware_available():
    response = Hardware.get_models_available()
    return response


@router.post("/u",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_operator)])
async def create_hardware(
        response: Response,
        payload: HardwareCreationPayload = Body(
            description="Information about the new hardware"),
        session: AsyncSession = Depends(get_session)
):
    hardware_dict = payload.model_dump()
    try:
        ecosystem_uid = hardware_dict.pop("ecosystem_uid")
        ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
        # TODO: check address before dispatching
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
                f"hardware '{hardware_dict['name']}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.get("/u/{uid}", response_model=HardwareInfo)
async def get_hardware(
        uid: str = uid_param,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    hardware = await hardware_or_abort(session, uid)
    return hardware


@router.put("/u/{uid}",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_hardware(
        response: Response,
        uid: str = uid_param,
        payload: HardwareUpdatePayload = Body(
            description="Updated information about the hardware"),
        session: AsyncSession = Depends(get_session)
):
    hardware_dict = payload.model_dump()
    try:
        hardware = await hardware_or_abort(session, uid)
        ecosystem = await Ecosystem.get(session, uid=hardware.ecosystem_uid)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.update,
                target="hardware",
                data=hardware_dict,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to update the hardware '{hardware.name}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send hardware update order to engine "
                f"for hardware '{id}'. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )


@router.delete("/u/{uid}",
               response_model=ResultResponse,
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_operator)])
async def delete_hardware(
        response: Response,
        uid: str = uid_param,
        session: AsyncSession = Depends(get_session)
):
    try:
        hardware = await hardware_or_abort(session, uid)
        ecosystem = await Ecosystem.get(session, uid=hardware.ecosystem_uid)
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.delete,
                target="hardware",
                data=uid,
            ).model_dump(),
            namespace="aggregator-internal",
        )
        return ResultResponse(
            msg=f"Request to delete the hardware '{hardware.name}' "
                f"successfully sent to engine '{ecosystem.engine_uid}'",
            status=ResultStatus.success
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to send delete order for hardware with uid '{uid}'. "
                f"Error msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure
        )
