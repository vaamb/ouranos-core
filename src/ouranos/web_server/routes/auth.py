from __future__ import annotations

import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from gaia_validators import safe_enum_from_name

from ouranos.core.config.consts import REGISTRATION_TOKEN_VALIDITY
from ouranos.core.database.models.app import (
    RoleName, User, UserMixin, UserTokenInfoDict)
from ouranos.core.exceptions import DuplicatedEntry
from ouranos.web_server.auth import (
    Authenticator, basic_auth, check_invitation_token, get_current_user,
    login_manager, is_admin)
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.auth import (
    LoginInfo, UserCreationPayload, UserInfo)
from ouranos.web_server.validate.base import BaseResponse


regex_email = re.compile(r"^[\-\w\.]+@([\w\-]+\.)+[\w\-]{2,4}$")  # Oversimplified but ok
regex_password = re.compile(
    # At least one lowercase, one capital letter, one number, one special char,
    #  and no space
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[-+_!$&?.,])(?=.{8,})[^ ]+$"
)


router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
    tags=["auth"],
)


@router.get("/login", response_model=LoginInfo)
async def login(
        remember: bool = False,
        authenticator: Authenticator = Depends(login_manager.get_authenticator),
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        session: AsyncSession = Depends(get_session),
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


@router.get("/logout", response_model=BaseResponse)
async def logout(
        authenticator: Authenticator = Depends(login_manager.get_authenticator),
        current_user: UserMixin = Depends(get_current_user),
):
    if current_user.is_anonymous:
        return BaseResponse(msg="You were not logged in")
    authenticator.logout()
    return BaseResponse(msg="Logged out")


@router.get("/current_user", response_model=UserInfo)
def get_current_user(
        current_user: UserMixin = Depends(get_current_user)
):
    return current_user


@router.post("/register",
             status_code=status.HTTP_201_CREATED,
             response_model=UserInfo)
async def register_new_user(
        invitation_token: str = Query(description="The invitation token received"),
        payload: UserCreationPayload = Body(
            description="Information about the new user"),
        authenticator: Authenticator = Depends(login_manager.get_authenticator),
        current_user: UserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="Logged in user cannot register"
        )
    token_payload = check_invitation_token(invitation_token)
    try:
        payload_dict = payload.model_dump()
        errors = []
        if token_payload.get("username"):
            payload_dict["username"] = token_payload["username"]
        username = payload_dict.pop("username")
        user = await User.get(session, username)
        if user is not None:
            errors.append("Username already used.")
        if token_payload.get("email"):
            payload_dict["email"] = token_payload["email"]
        email = payload_dict.pop("email")
        if not regex_email.match(email):
            errors.append("Wrong email format.")
        user = await User.get(session, email)
        if user is not None:
            errors.append("Email address already used.")
        password = payload_dict.pop("password")
        if not regex_password.match(password):
            errors.append("Wrong password format.")
        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=errors
            )
        payload_dict["role"] = token_payload.pop("role", None)
        await User.create(
            session, username, password, email=email, **payload_dict)
    except DuplicatedEntry as e:
        args = e.args[0]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=args
        )
    else:
        user = await User.get(session, username)
        authenticator.login(user, False)
        return user


@router.get("/registration_token", dependencies=[Depends(is_admin)])
async def create_registration_token(
        username: str = Query(
            default=None, description="The user name of the future user"),
        firstname: str = Query(
            default=None, description="The firstname of the future user"),
        lastname: str = Query(
            default=None, description="The lastname of the future user"),
        role: RoleName | str = Query(
            default=None, description="The role of the future user"),
        email: str = Query(
            default=None, description="The email address of the future user"),
        expires_in: int = Query(
            default=REGISTRATION_TOKEN_VALIDITY,
            description="The number of seconds before the token expires. "
                        "Default to one day."
        ),
        session: AsyncSession = Depends(get_session),
):
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
    return await User.create_invitation_token(
        session, user_info=user_info, expiration_delay=expires_in)
