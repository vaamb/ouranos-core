from __future__ import annotations

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, Response, status)
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import HardwareLevel, HardwareType

from ouranos.core.database.models.gaia import Ecosystem, Hardware
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.common_queries import (
    ecosystems_uid_q, hardware_level_q)
from ouranos.web_server.validate.payload.gaia import (
    HardwareCreationPayload, HardwareUpdatePayload)
from ouranos.web_server.validate.response.base import (
    ResultResponse, ResultStatus)
from ouranos.web_server.validate.response.gaia import (
    HardwareInfo, HardwareModelInfo)


router = APIRouter(
    prefix="/hardware",
    responses={404: {"description": "Not found"}},
    tags=["gaia/hardware"],
)


uid_param = Path(description="The uid of a hardware")

level_query = Query(
    default=None,
    description="The level at which the hardware operates"
)


async def hardware_or_abort(
        session: AsyncSession,
        hardware_uid: str
) -> Hardware:
    hardware = await Hardware.get(
        session=session, hardware_uid=hardware_uid
    )
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
        hardware_level: list[HardwareLevel] | None = hardware_level_q,
        hardware_type: list[HardwareType] | None = Query(
            default=None, description="A list of types of hardware"),
        hardware_model: list[str] | None = Query(
            default=None, description="A list of precise hardware model"),
        session: AsyncSession = Depends(get_session),
):
    hardware = await Hardware.get_multiple(
        session, hardware_uid, ecosystems_uid, hardware_level,
        hardware_type, hardware_model)
    return hardware


@router.get("/models_available", response_model=list[HardwareModelInfo])
async def get_hardware_available() -> list[str]:
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
    hardware_dict = payload.dict()
    try:
        # TODO: dispatch to Gaia
        ecosystem = await Ecosystem.get(session, hardware_dict["ecosystem_uid"])
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
    hardware_dict = payload.dict()
    try:
        hardware = await hardware_or_abort(session, uid)
        ecosystem = await Ecosystem.get(session, hardware.ecosystem_uid)
        # TODO: dispatch to Gaia
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
        ecosystem = await Ecosystem.get(session, hardware.ecosystem_uid)
        # TODO: dispatch to Gaia
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
