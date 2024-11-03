from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, status)
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher
import gaia_validators as gv

from ouranos.core.database.models.gaia import Ecosystem, Hardware
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.utils import (
    ecosystem_or_abort, h_level_desc, in_config_desc, uids_desc)
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
        *,
        hardware_uid: Annotated[
            list[str] | None,
            Query(description="A list of hardware uids"),
        ] = None,
        ecosystems_uid: Annotated[
            list[str] | None,
            Query(description=uids_desc),
        ] = None,
        hardware_level: Annotated[
            list[gv.HardwareLevel] | None,
            Query(description=h_level_desc),
        ] = None,
        hardware_type: Annotated[
            list[gv.HardwareType] | None,
            Query(description="A list of types of hardware"),
        ] = None,
        hardware_model: Annotated[
            list[str] | None,
            Query(description="A list of precise hardware model"),
        ] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
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
        payload: Annotated[
            HardwareCreationPayload,
            Body(description="Information about the new hardware"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
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
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send hardware creation order to engine for "
                f"hardware '{hardware_dict['name']}'. Error msg: "
                f"`{e.__class__.__name__}: {e}`",
            ),
        )


@router.get("/u/{uid}", response_model=HardwareInfo)
async def get_hardware(
        uid: Annotated[str, Path(description="The uid of a hardware")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    assert_single_uid(uid)
    hardware = await hardware_or_abort(session, uid)
    return hardware


@router.put("/u/{uid}",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_hardware(
        uid: Annotated[str, Path(description="The uid of a hardware")],
        payload: Annotated[
            HardwareUpdatePayload,
            Body(description="Updated information about the hardware"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
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
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send hardware update order to engine "
                f"for hardware '{id}'. Error msg: `{e.__class__.__name__}: "
                f"{e}`",
            ),
        )


@router.delete("/u/{uid}",
               response_model=ResultResponse,
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_operator)])
async def delete_hardware(
        uid: Annotated[str, Path(description="The uid of a hardware")],
        session: Annotated[AsyncSession, Depends(get_session)],
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
        HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Failed to send delete order for hardware with uid '{uid}'. "
                f"Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )
