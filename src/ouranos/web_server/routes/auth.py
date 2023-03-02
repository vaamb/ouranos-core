import re

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.validate.models.auth import AuthenticatedUser
from ouranos.sdk import api
from ouranos.sdk.api.exceptions import DuplicatedEntry
from ouranos.web_server.auth import (
    Authenticator, basic_auth, check_invitation_token, get_current_user,
    login_manager, is_admin
)
from ouranos.web_server.dependencies import get_session

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


@router.get("/login", response_model=validate.auth.login_response)
async def login(
        remember: bool = False,
        authenticator: Authenticator = Depends(login_manager),
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        session: AsyncSession = Depends(get_session),
):
    username = credentials.username
    password = credentials.password
    user = await authenticator.authenticate(session, username, password)
    token = authenticator.login(user, remember)
    return {
        "msg": "You are logged in",
        "data": {
            "user": user.dict(),
            "token": token,
        },
    }


@router.get("/logout", response_model=validate.common.simple_message)
async def logout(
        authenticator: Authenticator = Depends(login_manager),
        current_user: validate.auth.AuthenticatedUser = Depends(get_current_user),
):
    if current_user.is_anonymous:
        return validate.common.simple_message(msg="You were not logged in")
    authenticator.logout()
    return validate.common.simple_message(msg="Logged out")


@router.get("/current_user", response_model=validate.auth.CurrentUser)
def _get_current_user(
        current_user: validate.auth.AuthenticatedUser = Depends(get_current_user)
):
    return current_user.dict()


@router.post("/register", response_model=validate.auth.AuthenticatedUser)
async def register_new_user(
        invitation_token: str = Query(description="The invitation token received"),
        payload: validate.auth.user_creation = Body(
            description="Information about the new user"),
        authenticator: Authenticator = Depends(login_manager),
        current_user: validate.auth.AuthenticatedUser = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="Logged in user cannot register"
        )
    token_payload = check_invitation_token(invitation_token)
    try:
        payload_dict = payload.dict()
        errors = []
        username = payload_dict.pop("username")
        user = api.user.get(session, username)
        if user is not None:
            errors.append("Username already used.")
        email = payload_dict.pop("email")
        if not regex_email.match(email):
            errors.append("Wrong email format.")
        user = api.user.get(session, email)
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
        payload_dict["role"] = token_payload.pop("rle", None)
        user = await api.user.create(
            session, username, password, email=email, **payload_dict)
    except DuplicatedEntry as e:
        args = e.args[0]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=args
        )
    else:
        current_user = AuthenticatedUser.from_user(user)
        authenticator.login(current_user, False)
        return current_user.dict()


@router.get("/registration_token", dependencies=[Depends(is_admin)])
async def create_registration_token(
        role_name: str = Query(
            default=None, description="The name (with a capital letter) of the "
                                      "role the future user"),
        session: AsyncSession = Depends(get_session),
):
    return await api.auth.create_invitation_token(session, role_name)
