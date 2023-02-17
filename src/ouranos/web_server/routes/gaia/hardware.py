import typing as t

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.database.models.gaia import Hardware
from ouranos.sdk import api
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid


if t.TYPE_CHECKING:
    from ouranos.core.database.models.gaia import Hardware


router = APIRouter(
    prefix="/hardware",
    responses={404: {"description": "Not found"}},
    tags=["hardware"],
)


async def hardware_or_abort(
        session: AsyncSession,
        hardware_uid: str
) -> Hardware:
    hardware = await api.hardware.get(
        session=session, hardware_uid=hardware_uid
    )
    if hardware:
        return hardware
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No hardware found"
    )


@router.get("/", response_model=list[validate.gaia.hardware])
async def get_multiple_hardware(
        hardware_uid: t.Optional[list[str]] = Query(default=None),
        ecosystems_uid: t.Optional[list[str]] = Query(default=None),
        hardware_level: t.Optional[list[str]] = Query(default=None),
        hardware_type: t.Optional[list[str]] = Query(default=None),
        hardware_model: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session),
):
    hardware = await api.hardware.get_multiple(
        session, hardware_uid, ecosystems_uid, hardware_level,
        hardware_type, hardware_model
    )
    return hardware


@router.get("/models_available")
async def get_hardware_available() -> list[str]:
    response = api.hardware.get_models_available()
    return response


@router.post("/u", dependencies=[Depends(is_operator)])
async def create_hardware(
        payload: validate.gaia.hardware_creation,
        session: AsyncSession = Depends(get_session)
):
    await api.hardware.create(session, payload.dict())


@router.get("/u/<uid>", response_model=validate.gaia.hardware)
async def get_hardware(
        uid: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    hardware = await hardware_or_abort(session, uid)
    return hardware


@router.put("/u/<uid>", dependencies=[Depends(is_operator)])
async def update_hardware(
        uid: str,
        payload: validate.gaia.hardware_creation,
        session: AsyncSession = Depends(get_session)
):
    await api.hardware.update(session, payload.dict(), uid)


@router.delete("/u/<uid>", dependencies=[Depends(is_operator)])
async def delete_hardware(
        uid: str,
        session: AsyncSession = Depends(get_session)
):
    await api.hardware.delete(session, uid)

