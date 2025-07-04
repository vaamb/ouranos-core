# Strange bug: cannot use future annotations, somehow it enters in conflict with
#  FastAPI (via pydantic ?)
from datetime import datetime, timedelta, timezone
from hashlib import sha512
from typing import Awaitable, Callable, cast, Optional, Self, Union

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, ValidationError, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import current_app
from ouranos.core.config.consts import (
    LOGIN_NAME, SESSION_FRESHNESS, SESSION_TOKEN_VALIDITY)
from ouranos.core.database.models.app import (
    anonymous_user, Permission, User, UserMixin)
from ouranos.core.exceptions import (
    ExpiredTokenError, InvalidTokenError, TokenError)
from ouranos.core.utils import Tokenizer
from ouranos.web_server.dependencies import get_session


def _create_session_id(user_agent: str) -> str:
    h = sha512()
    h.update(user_agent.encode("utf8"))
    return h.hexdigest()


def check_token(invitation_token: str, token_sub: str) -> dict:
    try:
        payload = Tokenizer.loads(invitation_token)
        if (
                payload.get("sub") != token_sub
                or not payload.get("exp")
        ):
            raise InvalidTokenError
        return payload
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expired token"
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid token"
        )


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


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _get_exp_dt() -> datetime:
    return _now() + timedelta(seconds=SESSION_TOKEN_VALIDITY)


class SessionInfo(BaseModel):
    id: str
    user_id: int
    iat: datetime = Field(default_factory=_now)
    exp: datetime = Field(default_factory=_get_exp_dt)
    remember: bool = False

    @property
    def is_fresh(self) -> bool:
        time_limit = (
            datetime.now(timezone.utc).replace(microsecond=0)
            - timedelta(seconds=SESSION_FRESHNESS)
        )
        return self.iat < time_limit

    def refresh_iat(self) -> None:
        self.iat = _now()

    def refresh_exp(self) -> None:
        self.exp = _get_exp_dt()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "iat": self.iat,
            "exp": self.exp,
            "remember": self.remember is True,
        }

    def to_token(self) -> str:
        return Tokenizer.dumps(self.to_dict())

    @classmethod
    def from_token(
            cls,
            token: str,
    ) -> Self:
        return cls(**Tokenizer.loads(token))


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
        user_agent = self.request.headers.get("user-agent")
        session_id = _create_session_id(user_agent)
        session_info = SessionInfo(
            id=session_id, user_id=user.id, remember=remember)
        if session_info.remember:
            # Set a cookie expiration date
            expires = session_info.exp
        else:
            # Use a session cookie
            expires = None
        session_cookie = session_info.to_token()
        self.response.set_cookie(
            LOGIN_NAME.COOKIE.value, session_cookie, expires=expires, httponly=True)
        return session_cookie

    def logout(self) -> None:
        self.response.delete_cookie(LOGIN_NAME.COOKIE.value, httponly=True)


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
        request: Request,
        response: Response,
        auth: HTTPCredentials = Depends(cookie_bearer_auth),
) -> Optional[SessionInfo]:
    if auth.credentials is None:
        return None
    try:
        token = auth.credentials
        session_info = SessionInfo.from_token(token)
        user_agent = request.headers.get("user-agent")
        session_id = _create_session_id(user_agent)
        if session_id != session_info.id and not current_app.config["TESTING"]:
            raise TokenError
    except (TokenError, ValidationError):
        response.delete_cookie(LOGIN_NAME.COOKIE.value, httponly=True)
        return None
    else:
        return session_info


def refresh_session_cookie_expiration(
        session_info: Optional[SessionInfo],
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
        LOGIN_NAME.COOKIE.value, renewed_cookie, expires=expires, httponly=True)


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
