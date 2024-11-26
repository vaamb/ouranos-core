from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, status)
from sqlalchemy.ext.asyncio import AsyncSession

from dispatcher import AsyncDispatcher
import gaia_validators as gv

from ouranos.core.database.models.gaia import Hardware
from ouranos.core.dispatchers import DispatcherFactory
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.gaia.utils import (
    ecosystem_or_abort, eids_desc, euid_desc, h_level_desc, in_config_desc)
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.gaia.hardware import (
    HardwareType, HardwareInfo, HardwareModelInfo, HardwareUpdatePayload)


dispatcher: AsyncDispatcher = DispatcherFactory.get("application-internal")


router = APIRouter(
    prefix="/ecosystem",
    responses={404: {"description": "Not found"}},
    tags=["gaia/ecosystem/hardware"],
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


@router.get("/hardware", response_model=list[HardwareInfo])
async def get_multiple_hardware(
        *,
        hardware_uid: Annotated[
            list[str] | None,
            Query(description="A list of hardware uids"),
        ] = None,
        ecosystems_uid: Annotated[
            list[str] | None,
            Query(description=eids_desc),
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


@router.get("/hardware/types_available", response_model=list[HardwareType])
async def get_hardware_types_available():
    response = [
        {
            "name": hardware_type.name,
            "value": hardware_type.value
        }
        for hardware_type in gv.HardwareType.__members__.values()
    ]
    return response


@router.get("/hardware/models_available", response_model=list[HardwareModelInfo])
async def get_hardware_models_available():
    response = Hardware.get_models_available()
    return response


@router.get("/u/{ecosystem_uid}/hardware", response_model=list[HardwareInfo])
async def get_ecosystem_hardware(
        *,
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        hardware_type: Annotated[
            list[gv.HardwareType] | None,
            Query(description="A list of types of hardware"),
        ] = None,
        in_config: Annotated[bool | None, Query(description=in_config_desc)] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    hardware = await ecosystem.get_hardware(
        session, hardware_type=hardware_type, in_config=in_config)
    return hardware


@router.post("/u/{ecosystem_uid}/hardware/u",
             response_model=ResultResponse,
             status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(is_operator)])
async def create_hardware(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        payload: Annotated[
            gv.AnonymousHardwareConfig,
            Body(description="Information about the new hardware"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    hardware_dict = payload.model_dump()
    try:
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


@router.get("/u/{ecosystem_uid}/hardware/u/{hardware_uid}", response_model=HardwareInfo)
async def get_hardware(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        hardware_uid: Annotated[str, Path(description="The uid of a hardware")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    await ecosystem_or_abort(session, ecosystem_uid)
    hardware = await hardware_or_abort(session, hardware_uid)
    return hardware


@router.put("/u/{ecosystem_uid}/hardware/u/{hardware_uid}",
            response_model=ResultResponse,
            status_code=status.HTTP_202_ACCEPTED,
            dependencies=[Depends(is_operator)])
async def update_hardware(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        hardware_uid: Annotated[str, Path(description="The uid of a hardware")],
        payload: Annotated[
            HardwareUpdatePayload,
            Body(description="Updated information about the hardware"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    hardware = await hardware_or_abort(session, hardware_uid)
    hardware_dict = payload.model_dump()
    try:
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
                f"for hardware '{ecosystem_uid}'. Error msg: `{e.__class__.__name__}: "
                f"{e}`",
            ),
        )


@router.delete("/u/{ecosystem_uid}/hardware/u/{hardware_uid}",
               response_model=ResultResponse,
               status_code=status.HTTP_202_ACCEPTED,
               dependencies=[Depends(is_operator)])
async def delete_hardware(
        ecosystem_uid: Annotated[str, Path(description=euid_desc)],
        hardware_uid: Annotated[str, Path(description="The uid of a hardware")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    ecosystem = await ecosystem_or_abort(session, ecosystem_uid)
    hardware = await hardware_or_abort(session, hardware_uid)
    try:
        await dispatcher.emit(
            event="crud",
            data=gv.CrudPayload(
                routing=gv.Route(
                    engine_uid=ecosystem.engine_uid,
                    ecosystem_uid=ecosystem.uid
                ),
                action=gv.CrudAction.delete,
                target="hardware",
                data=hardware_uid,
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
                f"Failed to send delete order for hardware with uid '{hardware_uid}'. "
                f"Error msg: `{e.__class__.__name__}: {e}`",
            ),
        )
