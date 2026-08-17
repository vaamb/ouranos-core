# Strange bug: cannot use future annotations, somehow it enters in conflict with
#  FastAPI (via pydantic ?)
from typing import Awaitable, Callable, cast, Optional, Union

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import current_app
from ouranos.core.database.models.app import anonymous_user
from ouranos.core.config.consts import LOGIN_NAME
from ouranos.core.database.models.app import Permission, User, UserMixin
from ouranos.core.exceptions import TokenError
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.user_session import SessionInfo


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


class Authenticator:
    __slots__ = "login_manager", "request", "response"

    def __init__(
            self,
            login_manager: "LoginManager",
            request: Request,
            response: Response
    ):
        self.login_manager = login_manager
        self.request: Request = request
        self.response: Response = response

    async def authenticate(
            self,
            session: AsyncSession,
            username: str,
            password: str,
    ) -> User:
        user = await self.login_manager.get_user(session, user_id=username)
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
        self.response.set_cookie(
            LOGIN_NAME.COOKIE.value,
            session_cookie,
            expires=expires,
            secure=current_app.config["API_SECURE_COOKIES"],
            httponly=True,
        )
        return session_cookie

    def logout(self) -> None:
        self.response.delete_cookie(
            LOGIN_NAME.COOKIE.value,
            secure=current_app.config["API_SECURE_COOKIES"],
            httponly=True,
        )


class LoginManager:
    def __init__(self):
        self._user_callback = None

    def get_authenticator(
            self,
            request: Request,
            response: Response,
    ) -> Authenticator:
        return Authenticator(self, request, response)

    def user_loader(
            self,
            callback: Callable[[AsyncSession, Union[int, str]], Awaitable[UserMixin]]
    ) -> None:
        self._user_callback = callback

    def get_user(self, session: AsyncSession, user_id: Union[int, str]) -> Awaitable[UserMixin]:
        if self._user_callback:
            return self._user_callback(session, user_id)
        raise NotImplementedError(
            "Set your user_loader call back using `@login_manager.user_loader`"
        )


login_manager = LoginManager()


@login_manager.user_loader
async def load_user(
        session: AsyncSession,
        user_id: Optional[Union[int]]
) -> UserMixin:
    if user_id is None:
        return anonymous_user
    if isinstance(user_id, int):
        user = await User.get(session, user_id)
    else:
        user = await User.get_by(session, username=user_id)
    if user is None or not user.active:
        return anonymous_user
    return user


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
        response.delete_cookie(
            LOGIN_NAME.COOKIE.value,
            secure=current_app.config["API_SECURE_COOKIES"],
            httponly=True,
        )
        return None
    else:
        return session_info


def refresh_session_cookie_expiration(
        session_info: SessionInfo,
        response: Response,
) -> None:
    session_info.refresh_exp()
    if session_info.remember:
        # Refresh the cookie expiration date
        expires = session_info.exp
    else:
        # Keep a session cookie
        expires = None
    renewed_cookie = session_info.to_token()
    response.set_cookie(
        LOGIN_NAME.COOKIE.value,
        renewed_cookie,
        expires=expires,
        secure=current_app.config["API_SECURE_COOKIES"],
        httponly=True,
    )


async def get_current_user(
        session_info: Optional[SessionInfo] = Depends(get_session_info),
        session: AsyncSession = Depends(get_session),
) -> UserMixin:
    if session_info is None:
        return anonymous_user
    user_id = session_info.user_id
    user = await login_manager.get_user(session, user_id)
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


async def is_fresh(session_info: SessionInfo = Depends(get_session_info)) -> bool:
    return session_info.is_fresh
