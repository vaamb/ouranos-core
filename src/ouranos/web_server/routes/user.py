from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, Response, status)

from ouranos.core.database.models.app import (Permission, User, UserMixin)
from ouranos.web_server.auth import get_current_user, is_admin
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.base import ResultResponse, ResultStatus
from ouranos.web_server.validate.user import UserDescription, UserUpdatePayload


router = APIRouter(
    prefix="/user",
    responses={404: {"description": "Not found"}},
    tags=["user"],
)


def _safe_datetime(datetime_str: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(datetime_str)
    except TypeError:
        return None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dates should be entered in a valid ISO (8601) format.",
        )


async def get_user_or_abort(
        session: AsyncSession,
        username: str
) -> User:
    user = await User.get(session, user_id=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not find user with username '{username}'",
        )
    return user


@router.get("/",
            response_model=list[UserDescription],
            dependencies=[Depends(is_admin)])
async def get_users(
        registration_start_time: str = Query(
            default=None, description="ISO (8601) formatted datetime from "
                                      "which the research will be done"),
        registration_end_time: str = Query(
            default=None, description="ISO (8601) formatted datetime up to "
                                      "which the research will be done"),
        confirmed: bool = Query(default=False),
        active: bool = Query(default=False),
        page: int = Query(default=0),
        session: AsyncSession = Depends(get_session),
):
    registration_start_time: datetime | None = _safe_datetime(registration_start_time)
    registration_end_time: datetime | None = _safe_datetime(registration_end_time)
    users = await User.get_multiple(
        session, registration_start_time=registration_start_time,
        registration_end_time=registration_end_time, confirmed=confirmed,
        active=active, page=page)
    return users


@router.get("/u/{username}", response_model=UserDescription)
async def get_user(
        username: str = Path(description="The username of the user"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.username != username and not current_user.can(Permission.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only request your own profile",
        )
    user = await get_user_or_abort(session, username)
    return user


@router.put("/u/{username}",
            status_code=status.HTTP_202_ACCEPTED,
            response_model=ResultResponse)
async def update_user(
        response: Response,
        username: str = Path(description="The username of the user"),
        payload: UserUpdatePayload = Body(
            description="Updated information about the ecosystem"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.username != username and not current_user.can(Permission.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile",
        )

    user = await get_user_or_abort(session, username)
    if (
            current_user.username != user.username
            and user.role.permissions >= current_user.role.permissions
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update profiles with permissions lower than yours.",
        )
    user_dict = payload.model_dump()
    user_dict = {
        key: value for key, value in user_dict.items()
        if value is not None
    }
    try:
        await User.update(session, values=user_dict, user_id=username)
        return ResultResponse(
            msg=f"Successfully updated user '{username}''s info",
            status=ResultStatus.success,
        )
    except Exception as e:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return ResultResponse(
            msg=f"Failed to update user '{username}''s info. Error "
                f"msg: `{e.__class__.__name__}: {e}`",
            status=ResultStatus.failure,
        )


@router.delete("/u/{username}",
               status_code=status.HTTP_202_ACCEPTED,
               response_model=ResultResponse)
async def update_user(
        username: str = Path(description="The username of the user"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.username != username and not current_user.can(Permission.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own profile",
        )

    user = await get_user_or_abort(session, username)
    if (
            current_user.username != user.username
            and user.role.permissions >= current_user.role.permissions
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete profiles with permissions lower than yours.",
        )
    await User.delete(session, user_id=username)
    return ResultResponse(
        msg=f"User account of {username} has been deleted",
        status=ResultStatus.success,
    )


@router.post("/u/{username}/confirm",
             status_code=status.HTTP_202_ACCEPTED,
             response_model=ResultResponse)
async def update_user(
        username: str = Path(description="The username of the user"),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.username != username and not current_user.can(Permission.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only confirm your own profile",
        )

    user = await get_user_or_abort(session, username)
    if (
            current_user.username != user.username
            and user.role.permissions >= current_user.role.permissions
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only confirm profiles with permissions lower than yours.",
        )
    await User.update(session, user_id=username, values={"confirm": True})
    return ResultResponse(
        msg=f"User account of {username} has been deleted",
        status=ResultStatus.success,
    )
