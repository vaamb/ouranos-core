from __future__ import annotations

from datetime import datetime
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import (
    APIRouter, Body, Depends, HTTPException, Path, Query, status)

from ouranos.core.config.consts import REGISTRATION_TOKEN_VALIDITY
from ouranos.core.database.models.app import Permission, User, UserMixin
from ouranos.web_server.auth import get_current_user, is_admin
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import http_datetime
from ouranos.web_server.validate.user import UserDescription, UserUpdatePayload


router = APIRouter(
    prefix="/user",
    responses={404: {"description": "Not found"}},
    tags=["user"],
)


def check_current_user_is_allowed(current_user: UserMixin, username: str) -> None:
    if current_user.username != username and not current_user.can(Permission.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own profile",
        )


def check_current_user_is_higher(current_user: UserMixin, user: UserMixin) -> None:
    if (
            current_user.username != user.username
            and current_user.role.permissions <= user.role.permissions
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update other users info with permission level "
                   "lower than yours.",
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


@router.get("",
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
        per_page: Annotated[int, Query(le=100)] = 25,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    registration_start_time: datetime | None = http_datetime(registration_start_time)
    registration_end_time: datetime | None = http_datetime(registration_end_time)
    per_page = min(per_page, 100)
    users = await User.get_multiple(
        session, registration_start_time=registration_start_time,
        registration_end_time=registration_end_time, confirmed=confirmed,
        active=active, per_page=per_page, page=page)
    return users


@router.get("/u/{username}", response_model=UserDescription)
async def get_user(
        username: Annotated[str, Path(description="The username of the user")],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    check_current_user_is_allowed(current_user, username)
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
    check_current_user_is_allowed(current_user, username)
    user = await get_user_or_abort(session, username)
    check_current_user_is_higher(current_user, user)

    user_dict = payload.model_dump(exclude_defaults=True)
    user_dict = {
        key: value for key, value in user_dict.items()
        if value != getattr(user, key)
    }
    try:
        await User.update(session, user_id=user.id, values=user_dict)
        return f"Successfully updated {username}'s info"
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.args
        )


@router.get("/u/{username}/confirmation_token")
async def create_confirmation_token(
        *,
        username: Annotated[str, Path(description="The username of the user")],
        send_email: Annotated[
            bool,
            Query(
                description="Whether to send an email to the user. "
                            "Default to False."
            ),
        ] = False,
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    check_current_user_is_allowed(current_user, username)
    user = await get_user_or_abort(session, username)
    check_current_user_is_higher(current_user, user)

    try:
        token = await user.create_confirmation_token(
            expiration_delay=REGISTRATION_TOKEN_VALIDITY)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    if send_email:
        try:
            await user.send_confirmation_email(token, REGISTRATION_TOKEN_VALIDITY)
        except NotImplementedError as e:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=str(e),
            )
        return f"Successfully sent an email to confirm {username}'s account"
    return token


@router.get("/u/{username}/password_reset_token")
async def create_password_reset_token(
        *,
        username: Annotated[str, Path(description="The username of the user")],
        send_email: Annotated[
            bool,
            Query(
                description="Whether to send an email to the user. "
                            "Default to False."
            ),
        ] = False,
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    check_current_user_is_allowed(current_user, username)
    user = await get_user_or_abort(session, username)
    check_current_user_is_higher(current_user, user)

    try:
        token = await user.create_password_reset_token(
            expiration_delay=REGISTRATION_TOKEN_VALIDITY)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    if send_email:
        try:
            await user.send_reset_password_email(token, REGISTRATION_TOKEN_VALIDITY)
        except NotImplementedError as e:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=str(e),
            )
        return f"Successfully sent an email to reset {username}'s password"
    return token
