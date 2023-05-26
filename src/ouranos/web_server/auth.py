# Strange bug: cannot use future annotations, somehow it enters in conflict with
#  FastAPI (via pydantic ?)
from hashlib import sha512
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core import validate
from ouranos.core.config.consts import LOGIN_NAME, TOKEN_SUBS
from ouranos.core.database.models.app import Permission, User
from ouranos.core.exceptions import (
    ExpiredTokenError, InvalidTokenError, TokenError)
from ouranos.core.utils import Tokenizer
from ouranos.core.validate.models.auth import (
    anonymous_user, AuthenticatedUser, CurrentUser)
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


class HTTPCookieBearer(HTTPBearer):
    async def __call__(self, request: Request) -> validate.auth.HTTPCredentials:
        session_cookie = request.cookies.get(LOGIN_NAME.COOKIE.value)
        if session_cookie is not None:
            return validate.auth.HTTPCredentials(credentials=session_cookie)
        authorization_header = request.headers.get(LOGIN_NAME.HEADER.value)
        if authorization_header is not None:
            scheme, credentials = get_authorization_scheme_param(authorization_header)
            return validate.auth.HTTPCredentials(credentials=credentials)
        return validate.auth.HTTPCredentials(credentials=None)


basic_auth = HTTPBasic()
cookie_bearer_auth = HTTPCookieBearer()


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
    ) -> AuthenticatedUser:
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
        return AuthenticatedUser.from_user(user)

    def login(self, user: AuthenticatedUser, remember: bool) -> str:
        remote_address = self.request.client.host
        user_agent = self.request.headers.get("user-agent")
        session_id = _create_session_id(remote_address, user_agent)
        payload = validate.auth.TokenPayload(
            id=session_id, user_id=user.id, remember=remember
        )
        token = payload.to_token(refresh_iat=True)
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

    def get_user(self, user_id: int, session) -> AuthenticatedUser:
        if self._user_callback:
            return self._user_callback(user_id, session)
        raise NotImplementedError(
            "Set your user_loader call back using `@login_manager.user_loader`"
        )


login_manager = LoginManager()


@login_manager.user_loader
async def load_user(user_id: Optional[int], session: AsyncSession) -> User:
    return await User.get(session, user_id)


async def get_current_user(
        request: Request,
        response: Response,
        auth: validate.auth.HTTPCredentials = Depends(cookie_bearer_auth),
        session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    if auth.credentials is None:
        return anonymous_user
    try:
        token = auth.credentials
        payload = validate.auth.TokenPayload.from_token(token)
        session_id = _create_session_id(
            request.client.host, request.headers.get("user-agent")
        )
        if session_id != payload.id and request.client.host != "127.0.0.1":
            raise TokenError
    except (TokenError, ValidationError):
        response.delete_cookie(LOGIN_NAME.COOKIE.value)
        return anonymous_user
    else:
        user_id = payload.user_id
        user = await login_manager.get_user(user_id, session)
        # Reset the token exp field
        renewed_token = payload.to_token()
        response.set_cookie(LOGIN_NAME.COOKIE.value, renewed_token, httponly=True)
        return AuthenticatedUser.from_user(user)


async def user_can(user: CurrentUser, permission: Permission):
    if not user.can(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot access this resource.",
        )
    return True


# In case we would like to put a restriction for all routes
async def base_restriction(current_user: CurrentUser = Depends(get_current_user)) -> bool:
    return True


async def is_authenticated(current_user: CurrentUser = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.VIEW)


async def is_operator(current_user: AuthenticatedUser = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.OPERATE)


async def is_admin(current_user: CurrentUser = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.ADMIN)


async def is_fresh(current_user: CurrentUser = Depends(get_current_user)) -> bool:
    return current_user.is_fresh()
