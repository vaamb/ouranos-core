from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import safe_enum_from_name

from ouranos.core.config.consts import REGISTRATION_TOKEN_VALIDITY, TOKEN_SUBS
from ouranos.core.database.models.app import (
    anonymous_user, RoleName, User, UserMixin, UserTokenInfoDict)
from ouranos.web_server.auth import (
    Authenticator, basic_auth, check_token, get_current_user,
    login_manager, is_admin)
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.auth import (
    LoginInfo, UserCreationPayload, UserPasswordUpdatePayload, UserInfo)


router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
    tags=["auth"],
)


@router.get("/login", response_model=LoginInfo)
async def login(
        *,
        remember: Annotated[
            bool | None,
            Query(description="Remember the session"),
        ] = False,
        authenticator: Annotated[
            Authenticator,
            Depends(login_manager.get_authenticator),
        ],
        credentials: Annotated[HTTPBasicCredentials, Depends(basic_auth)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    username = credentials.username
    password = credentials.password
    user = await authenticator.authenticate(session, username, password)
    token = authenticator.login(user, remember)
    return {
        "msg": "You are logged in",
        "user": user,
        "session_token": token,
    }


@router.get("/logout")
async def logout(
        authenticator: Annotated[Authenticator, Depends(login_manager.get_authenticator)],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
):
    if current_user.is_anonymous:
        return "You were not logged in"
    authenticator.logout()
    return "Logged out"


@router.get("/current_user", response_model=UserInfo)
async def get_current_user_info(
        current_user: UserMixin = Depends(get_current_user),  # Cannot use Annotated here
):
    return current_user


@router.put("/current_user", response_model=UserInfo)
async def update_current_user_info(
        *,
        current_user: UserMixin = Depends(get_current_user),  # Cannot use Annotated here
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if current_user != anonymous_user:
        await User.update(
            session,
            user_id=current_user.id,
            values={"last_seen": datetime.now(timezone.utc)}
        )


@router.post("/register",
             status_code=status.HTTP_201_CREATED,
             response_model=LoginInfo)
async def register_new_user(
        *,
        invitation_token: Annotated[
            str,
            Query(description="The invitation token received"),
        ],
        payload: Annotated[
            UserCreationPayload,
            Body(description="Information about the new user"),
        ],
        send_email: Annotated[
            bool,
            Query(
                description="Whether to send a welcome email to the user. "
                            "Default to False."
            ),
        ] = False,
        authenticator: Annotated[Authenticator, Depends(login_manager.get_authenticator)],
        current_user: Annotated[UserMixin, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if current_user.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="Logged in user cannot register"
        )
    token_payload = check_token(invitation_token, TOKEN_SUBS.REGISTRATION.value)
    payload_dict = payload.model_dump()
    # Make sure token info are used
    if "username" in token_payload:
        payload_dict["username"] = token_payload["username"]
    if "email" in token_payload:
        payload_dict["email"] = token_payload["email"]
    if "role" in token_payload:
        payload_dict["role"] = token_payload["role"]
    try:
        await User.create(session, values=payload_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.args
        )
    else:
        user = await User.get_by(session, username=payload_dict["username"])
        token = authenticator.login(user, False)
        if send_email:
            try:
                await user.send_confirmation_email()
            except NotImplementedError as e:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail=str(e),
                )
        return {
            "msg": "You are registered.",
            "user": user,
            "session_token": token,
        }


@router.post("/confirm_account")
async def reset_password(
        token: Annotated[
            str,
            Query(description="The confirmation token received"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    check_token(token, TOKEN_SUBS.CONFIRMATION.value)
    try:
        await User.confirm(session, token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    else:
        return {"msg": "Your account has been confirmed."}


@router.post("/reset_password")
async def reset_password(
        token: Annotated[
            str,
            Query(description="The reset token received"),
        ],
        payload: Annotated[
            UserPasswordUpdatePayload,
            Body(description="Updated password"),
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    check_token(token, TOKEN_SUBS.RESET_PASSWORD.value)
    try:
        await User.reset_password(session, token, payload.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) if not e.args else e.args[0]  # There should be a single error
        )
    else:
        return {"msg": "Your password has been changed."}


@router.get("/registration_token", dependencies=[Depends(is_admin)])
async def create_registration_token(
        *,
        username: Annotated[
            str,
            Query(description="The user name of the future user")
        ] = None,
        firstname: Annotated[
            str,
            Query(description="The firstname of the future user"),
        ] = None,
        lastname: Annotated[
            str,
            Query(description="The lastname of the future user"),
        ] = None,
        role: Annotated[
            RoleName | str,
            Query(description="The role of the future user"),
        ] = None,
        email: Annotated[
            str,
            Query(description="The email address of the future user"),
        ] = None,
        expires_in: Annotated[
            int,
            Query(
                description="The number of seconds before the token expires. "
                            "Default to one day."
            ),
        ] = REGISTRATION_TOKEN_VALIDITY,
        send_email: Annotated[
            bool,
            Query(
                description="Whether to send an email to the user. "
                            "Default to False."
            ),
        ] = False,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    if send_email and email is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email address is required to send an invitation",
        )
    if role is not None:
        try:
            role = safe_enum_from_name(RoleName, role)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid role"
            )
    user_info: UserTokenInfoDict = {
        "username": username,
        "firstname": firstname,
        "lastname": lastname,
        "role": role,
        "email": email,
    }
    token = await User.create_invitation_token(
        session, user_info=user_info, expiration_delay=expires_in)
    if send_email:
        try:
            await User.send_invitation_email(session, user_info=user_info, token=token)
        except NotImplementedError as e:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=str(e),
            )
    return token
