from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, status)

from ouranos.core.database.models.app import Permission, User, UserMixin
from ouranos.web_server.auth import get_current_user, is_admin
from ouranos.web_server.dependencies import get_session
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
    user = await User.get_by(session, username=username, active=True)
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
        *,
        registration_start_time: Annotated[
            str,
            Query(description=(
                "ISO (8601) formatted datetime from which the research will be "
                "done"
            )),
        ] = None,
        registration_end_time:Annotated[
            str,
            Query(description=(
                "ISO (8601) formatted datetime up to which the research will be "
                "done"
            )),
        ] = None,
        confirmed: Annotated[bool, Query()] = False,
        active: Annotated[bool, Query()] = False,
        page: Annotated[int, Query()] = 0,
        session: Annotated[AsyncSession, Depends(get_session)],
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
        username: Annotated[str, Path(description="The username of the user")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if current_user.username != username and not current_user.can(Permission.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only request your own profile",
        )
    user = await get_user_or_abort(session, username)
    return user


@router.put("/u/{username}",
            status_code=status.HTTP_202_ACCEPTED)
async def update_user(
        username: Annotated[str, Path(description="The username of the user")],
        payload: Annotated[
            UserUpdatePayload,
            Body(description="Updated information about the ecosystem"),
        ],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
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
    user_dict = payload.model_dump(exclude_defaults=True)
    user_dict = {
        key: value for key, value in user_dict.items()
        if value != getattr(user, key)
    }
    try:
        await User.update(session, user_id=user.id, values=user_dict)
        return f"Successfully updated user '{username}''s info"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.args
        )
