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
        invitation_token: str = Query(),
        payload: validate.auth.user_creation = Body(),
        authenticator: Authenticator = Depends(login_manager),
        current_user: validate.auth.AuthenticatedUser = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.is_authenticated:
        return {"msg": "You cannot register, you are already logged in"}
    token_payload = check_invitation_token(invitation_token)
    try:
        payload_dict = payload.dict()
        username = payload_dict.pop("username")
        password = payload_dict.pop("password")
        payload_dict["role"] = token_payload.pop("rle", None)
        user = await api.user.create(session, username, password, **payload_dict)
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
        role_name: str = Query(default=None),
        session: AsyncSession = Depends(get_session),
):
    return await api.auth.create_invitation_token(session, role_name)
