# Strange bug: cannot use future annotations, somehow it enters in conflict with
#  FastAPI (via pydantic ?)
from datetime import datetime, timedelta, timezone
from hashlib import sha512
from typing import Optional, Self

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, ValidationError, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos import current_app
from ouranos.core.config.consts import (
    LOGIN_NAME, SESSION_FRESHNESS, SESSION_TOKEN_VALIDITY, TOKEN_SUBS)
from ouranos.core.database.models.app import (
    anonymous_user, Permission, User, UserMixin)
from ouranos.core.exceptions import (
    ExpiredTokenError, InvalidTokenError, TokenError)
from ouranos.core.utils import Tokenizer
from ouranos.web_server.dependencies import get_session


def _create_session_id(remote_address, user_agent):
    base = f"{remote_address}|{user_agent}"
    h = sha512()
    h.update(base.encode("utf8"))
    return h.hexdigest()


def check_invitation_token(invitation_token: str) -> dict:
    try:
        payload = Tokenizer.loads(invitation_token)
        if (
                payload.get("sub") != TOKEN_SUBS.REGISTRATION.value
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


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


class SessionInfo(BaseModel):
    id: str
    user_id: int
    iat: datetime = Field(default_factory=_now)
    remember: bool = False

    @property
    def is_fresh(self) -> bool:
        time_limit = (
            datetime.now(timezone.utc).replace(microsecond=0)
            - timedelta(seconds=SESSION_FRESHNESS)
        )
        return self.iat < time_limit

    def to_dict(self, refresh_iat: bool = False) -> dict:
        if refresh_iat:
            iat = datetime.now(timezone.utc).replace(microsecond=0)
        else:
            iat = self.iat
        return {
            "id": self.id,
            "user_id": self.user_id,
            "iat": iat,
            "exp": (
                datetime.now(timezone.utc).replace(microsecond=0)
                + timedelta(seconds=SESSION_TOKEN_VALIDITY)
            ),
            "remember": self.remember is True,
        }

    def to_token(
            self,
            refresh_iat: bool = False,
    ) -> str:
        return Tokenizer.dumps(self.to_dict(refresh_iat))

    @classmethod
    def from_token(
            cls,
            token: str,
    ) -> Self:
        return cls(**Tokenizer.loads(token))


class Authenticator:
    __slots__ = "_session", "request", "response"

    def __init__(
            self,
            session: AsyncSession,
            request: Request,
            response: Response
    ):
        self._session: AsyncSession = session
        self.request: Request = request
        self.response: Response = response

    async def authenticate(
            self,
            session: AsyncSession,
            username: str,
            password: str,
    ) -> User:
        user = await User.get(session, username)
        try:
            password_correct = user.check_password(password)
        except AttributeError:  # empty password
            password_correct = False
        if user is None or not password_correct:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Basic"},
            )
        return user

    def login(self, user: User, remember: bool) -> str:
        remote_address = self.request.client.host
        user_agent = self.request.headers.get("user-agent")
        session_id = _create_session_id(remote_address, user_agent)
        session_info = SessionInfo(
            id=session_id, user_id=user.id, remember=remember)
        token = session_info.to_token(refresh_iat=True)
        self.response.set_cookie(LOGIN_NAME.COOKIE.value, token, httponly=True)
        return token

    def logout(self) -> None:
        self.response.delete_cookie(LOGIN_NAME.COOKIE.value)


class LoginManager:
    def __init__(self):
        self._user_callback = None

    def __call__(
            self,
            request: Request,
            response: Response,
            session: AsyncSession = Depends(get_session)
    ) -> Authenticator:
        return Authenticator(session, request, response)

    def user_loader(self, callback) -> None:
        self._user_callback = callback

    def get_user(self, user_id: int, session) -> UserMixin:
        if self._user_callback:
            return self._user_callback(user_id, session)
        raise NotImplementedError(
            "Set your user_loader call back using `@login_manager.user_loader`"
        )


login_manager = LoginManager()


@login_manager.user_loader
async def load_user(user_id: Optional[int], session: AsyncSession) -> UserMixin:
    user = await User.get(session, user_id)
    if user is None:
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
        session_id = _create_session_id(
            request.client.host, request.headers.get("user-agent"))
        if session_id != session_info.id and not current_app.config["TESTING"]:
            raise TokenError
    except (TokenError, ValidationError):
        response.delete_cookie(LOGIN_NAME.COOKIE.value)
        return None
    else:
        # Reset the token exp field
        renewed_token = session_info.to_token()
        response.set_cookie(LOGIN_NAME.COOKIE.value, renewed_token, httponly=True)
        return session_info


async def get_current_user(
        session_info: Optional[SessionInfo] = Depends(get_session_info),
        session: AsyncSession = Depends(get_session),
) -> UserMixin:
    if session_info is None:
        return anonymous_user
    user_id = session_info.user_id
    user = await login_manager.get_user(user_id, session)
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
