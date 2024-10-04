from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.gaia import CameraPicture
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.gaia.utils import ecosystems_uid_q
from ouranos.web_server.validate.gaia.pictures import CameraPictureInfo


router = APIRouter(
    prefix="/camera_picture_info",
    responses={404: {"description": "Not found"}},
    tags=["gaia/camera_picture_info"],
)


@router.get("/", response_model=list[CameraPictureInfo])
async def get_multiple_camera_picture_info(
    ecosystems_uid: list[str] | None = ecosystems_uid_q,
    cameras_uid: list[str] | None = Query(
            default=None, description="A list of camera uids"),
    session: AsyncSession = Depends(get_session),
):
    pictures_info = await CameraPicture.get_multiple(
        session, ecosystem_uid=ecosystems_uid, camera_uid=cameras_uid)
    return pictures_info


@router.get("/u/{ecosystem_uid}", response_model=list[CameraPictureInfo])
async def get_camera_picture_info_for_ecosystem(
        ecosystem_uid: str = Path(description="An ecosystem uid"),
        cameras_uid: list[str] | None = Query(
            default=None, description="A list of camera uids"),
        session: AsyncSession = Depends(get_session)
):
    pictures_info = await CameraPicture.get_multiple(
        session, ecosystem_uid=ecosystem_uid, camera_uid=cameras_uid)
    return pictures_info


@router.get("/u/{ecosystem_uid}/{camera_uid}", response_model=CameraPictureInfo)
async def get_camera_picture_info(
        ecosystem_uid: str = Path(description="An ecosystem uid"),
        camera_uid: str = Path(description="A camera uid"),
        session: AsyncSession = Depends(get_session)
):
    picture_info = await CameraPicture.get(
        session, ecosystem_uid=ecosystem_uid, camera_uid=camera_uid)
    if not picture_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No ecosystem(s) found"
        )
    return picture_info