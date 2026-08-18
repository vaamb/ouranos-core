# Strange bug: cannot use future annotations, somehow it enters in conflict with
#  FastAPI (via pydantic ?)
from datetime import datetime
from typing import cast, Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import current_app
from ouranos.core.config.consts import LOGIN_NAME
from ouranos.core.database.models.app import Permission, User, UserMixin
from ouranos.core.exceptions import TokenError
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.user_session import (
    get_user, get_user_from_session_info, SessionInfo)


class HTTPCredentials(BaseModel):
    credentials: Optional[str]


class HTTPCookieBearer(HTTPBearer):
    async def __call__(self, request: Request) -> HTTPCredentials:
        session_cookie = request.cookies.get(LOGIN_NAME.COOKIE.value)
        if session_cookie is not None:
            return HTTPCredentials(credentials=session_cookie)
        authorization_header = request.headers.get(LOGIN_NAME.HEADER.value)
        if authorization_header is not None:
            scheme, credentials = get_authorization_scheme_param(authorization_header)
            return HTTPCredentials(credentials=credentials)
        return HTTPCredentials(credentials=None)


basic_auth = HTTPBasic()
cookie_bearer_auth = HTTPCookieBearer()


def set_session_cookie(
        response: Response,
        value: str,
        max_age: int | None = None,
        expires: datetime | str | int | None = None,
) -> None:
    response.set_cookie(
        LOGIN_NAME.COOKIE.value,
        value,
        max_age=max_age,
        expires=expires,
        secure=current_app.config["API_SECURE_COOKIES"],
        httponly=True,
    )


def delete_session_cookie(response: Response) -> None:
    set_session_cookie(response, "", max_age=0, expires=0)


class Authenticator:
    __slots__ = ("response", )

    def __init__(
            self,
            response: Response
    ):
        self.response: Response = response

    async def authenticate(
            self,
            session: AsyncSession,
            username: str,
            password: str,
    ) -> User:
        user = await get_user(session, username)
        if not user.check_password(password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Basic"},
            )
        user = cast(User, user)
        return user

    def login(self, user: User, remember: bool) -> str:
        session_info = SessionInfo(user_id=user.id, remember=remember)
        if session_info.remember:
            # Set a cookie expiration date
            expires = session_info.exp
        else:
            # Use a session cookie
            expires = None
        session_cookie = session_info.to_token()
        set_session_cookie(self.response, session_cookie, expires=expires)
        return session_cookie

    def logout(self) -> None:
        delete_session_cookie(self.response)


def get_authenticator(response: Response) -> Authenticator:
    return Authenticator(response)


def get_session_info(
        response: Response,
        auth: HTTPCredentials = Depends(cookie_bearer_auth),
) -> Optional[SessionInfo]:
    token = auth.credentials
    if token is None:
        return None
    try:
        session_info = SessionInfo.from_token(token)
    except TokenError:
        delete_session_cookie(response)
        return None
    else:
        return session_info


def _reissue_session_cookie(
        session_info: SessionInfo,
        response: Response,
) -> None:
    # Get the expiration date so the refreshed token has the correct expiration date
    if session_info.remember:
        expires = session_info.exp
    else:
        # Keep a session cookie
        expires = None
    extended_cookie = session_info.to_token()
    set_session_cookie(response, extended_cookie, expires=expires)


def extend_session_cookie(
        session_info: SessionInfo,
        response: Response,
) -> None:
    session_info.refresh_exp()
    _reissue_session_cookie(session_info, response)


def refresh_session_cookie(
        session_info: SessionInfo,
        response: Response,
) -> None:
    session_info.refresh_iat()
    _reissue_session_cookie(session_info, response)


async def get_current_user(
        session_info: Optional[SessionInfo] = Depends(get_session_info),
        session: AsyncSession = Depends(get_session),
) -> UserMixin:
    user = await get_user_from_session_info(session, session_info)
    return user


async def user_can(user: UserMixin, permission: Permission):
    if not user.can(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot access this resource.",
        )
    return True


# In case we would like to put a restriction for all routes
async def base_restriction(current_user: UserMixin = Depends(get_current_user)) -> bool:
    return True


async def is_authenticated(current_user: UserMixin = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.VIEW)


async def is_operator(current_user: UserMixin = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.OPERATE)


async def is_admin(current_user: UserMixin = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.ADMIN)


async def is_fresh(session_info: Optional[SessionInfo] = Depends(get_session_info)) -> None:
    if session_info is None or not session_info.is_fresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This requires a fresh session.",
        )
