from datetime import datetime
from hashlib import sha512
import typing as t

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.dependencies import get_session
from src.core import api
from src.core.database.models.app import anonymous_user, Permission, User
from src.core.utils import Tokenizer


LOGIN_COOKIE_NAME = "Authorization"
FRESH_TIME_DELTA = 15 * 60
TOKEN_VALIDITY = 15 * 60


def _create_session_id(remote_address, user_agent):
    base = f"{remote_address}|{user_agent}"
    h = sha512()
    h.update(base.encode("utf8"))
    return h.hexdigest()


class HTTPCookieBearer(HTTPBearer):
    async def __call__(self, request: Request) -> t.Optional[str]:
        authorization_cookie: str = request.cookies.get(LOGIN_COOKIE_NAME)
        authorization_header: str = request.headers.get(LOGIN_COOKIE_NAME)
        for authorization in (authorization_cookie, authorization_header):
            if not authorization:
                continue
            scheme, param = get_authorization_scheme_param(authorization)
            if scheme.lower() == "bearer":
                return param
        return None


basic_auth = HTTPBasic()
cookie_bearer_auth = HTTPCookieBearer()


class Authenticator:
    __slots__ = "_secret_key", "_session", "request", "response"

    def __init__(self, login_manager: "LoginManager", session, request, response):
        self._secret_key = login_manager._secret_key
        self._session = session
        self.request = request
        self.response = response

    async def authenticate(
            self,
            session: AsyncSession,
            username: str,
            password: str,
    ) -> User:
        user = await api.user.get(session, username)
        if user is None or not user.check_password(password):
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
        payload = {
            "id": session_id,
            "user_id": user.id,
            "iat": datetime.utcnow().timestamp()
        }
        if remember:
            payload.update({"remember": remember})
        token = Tokenizer.dumps(payload, secret_key=self._secret_key)
        self.response.set_cookie(LOGIN_COOKIE_NAME, f"Bearer {token}", httponly=True)
        return token

    def logout(self) -> None:
        self.response.delete_cookie(LOGIN_COOKIE_NAME)


class LoginManager:
    def __init__(self, config: dict = None):
        self._secret_key = None
        self._user_callback = None
        if config:
            self.init(config)

    def __call__(
            self,
            request: Request,
            response: Response,
            session: AsyncSession = Depends(get_session)
    ) -> Authenticator:
        return Authenticator(self, session, request, response)

    def init(self, config):
        self._secret_key = config.get("SECRET_KEY")
        if not self._secret_key:
            raise RuntimeError("config must have an entry 'SECRET_KEY'")

    def user_loader(self, callback) -> None:
        self._user_callback = callback

    def get_user(self, user_id: int, session) -> User:
        if self._user_callback:
            return self._user_callback(user_id, session)
        raise NotImplementedError(
            "Set your user_loader call back using `@login_manager.user_loader`"
        )


login_manager = LoginManager()


@login_manager.user_loader
async def load_user(user_id: int, session: AsyncSession) -> User:
    user = await api.user.get(session, user_id)
    return user


async def _get_current_user(
        response: Response,
        #get_user=Depends(login_manager.get_user),
        session: AsyncSession = Depends(get_session),
        token: str = Depends(cookie_bearer_auth),
) -> User:
    if not token:
        return anonymous_user
    try:
        payload = Tokenizer.loads(token)
        user_id = payload.get("user_id", None)
    except jwt.PyJWTError:
        response.delete_cookie(LOGIN_COOKIE_NAME)
        return anonymous_user
    else:
        user = await login_manager.get_user(user_id, session)
        if user:
            """iat = payload["iat"]
            remember = payload.get("remember", False)
            fresh = datetime.now().timestamp() - iat < FRESH_TIME_DELTA
            if not fresh and not remember:
                response.delete_cookie(LOGIN_COOKIE_NAME)
                return anonymous_user  # TODO: use a msg asking for re login"""
            return user
        return anonymous_user


async def get_current_user(user: User = Depends(_get_current_user)) -> User:
    return user


async def user_can(user: User, permission: int):
    if not user.can(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot access this resource",
        )
    return True


async def base_restriction(current_user: User = Depends(get_current_user)) -> bool:
    return True


async def is_authenticated(current_user: User = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.VIEW)


async def is_operator(current_user: User = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.ADMIN)


async def is_admin(current_user: User = Depends(get_current_user)) -> bool:
    return await user_can(current_user, Permission.ADMIN)
