from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import HardwareLevel, HardwareType

from ouranos.core import validate
from ouranos.core.database.models.gaia import Hardware
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.routes.gaia.common_queries import (
    ecosystems_uid_q, hardware_level_q)


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


@router.get("", response_model=list[validate.gaia.hardware])
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


@router.get("/models_available")
async def get_hardware_available() -> list[str]:
    response = Hardware.get_models_available()
    return response


@router.post("/u", dependencies=[Depends(is_operator)])
async def create_hardware(
        payload: validate.gaia.hardware_creation = Body(
            description="Information about the new hardware"),
        session: AsyncSession = Depends(get_session)
):
    await Hardware.create(session, payload.dict())


@router.get("/u/{uid}", response_model=validate.gaia.hardware)
async def get_hardware(
        uid: str = uid_param,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    hardware = await hardware_or_abort(session, uid)
    return hardware


@router.put("/u/{uid}", dependencies=[Depends(is_operator)])
async def update_hardware(
        uid: str = uid_param,
        payload: validate.gaia.hardware_creation = Body(
            description="Updated information about the hardware"),
        session: AsyncSession = Depends(get_session)
):
    await Hardware.update(session, payload.dict(), uid)


@router.delete("/u/{uid}", dependencies=[Depends(is_operator)])
async def delete_hardware(
        uid: str = uid_param,
        session: AsyncSession = Depends(get_session)
):
    await Hardware.delete(session, uid)

