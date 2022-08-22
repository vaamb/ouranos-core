from datetime import datetime
from hashlib import sha512
import typing as t

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
import jwt
from sqlalchemy.orm import Session

from src.app.dependencies import get_session
from src.database.models.app import anonymous_user, Permission, User, UserMixin
from src.utils import Tokenizer


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

    def authenticate(
            self,
            username: str,
            password: str,
            session=Depends(get_session)
    ) -> User:
        user = self._session.query(User).filter_by(username=username).first()
        if user is None or not user.check_password(password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Basic"},
            )
        return user

    def login(self, user: User, remember: bool) -> None:
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
            session=Depends(get_session)
    ) -> Authenticator:
        return Authenticator(self, session, request, response)

    def init(self, config):
        self._secret_key = config.get("SECRET_KEY")
        if not self._secret_key:
            raise RuntimeError("config must have an entry 'SECRET_KEY'")

    def user_loader(self, callback) -> None:
        self._user_callback = callback

    def get_user(self, user_id: int, session) -> User:
        print(1)
        if self._user_callback:
            return self._user_callback(user_id, session)
        raise NotImplementedError(
            "Set your user_loader call back using `@login_manager.user_loader`"
        )


# TODO: use async
login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id: int, session: Session) -> User:
    return session.query(User).filter_by(id=user_id).one_or_none()


async def _get_current_user(
        response: Response,
        #get_user=Depends(login_manager.get_user),
        session=Depends(get_session),
        token: str = Depends(cookie_bearer_auth),
) -> User:
    if not token:
        return anonymous_user
    try:
        payload = Tokenizer.loads(token)
        user_id = payload.get("user_id", None)
    except jwt.PyJWTError:
        response.delete_cookie(LOGIN_COOKIE_NAME)
        return anonymous_user  # TODO: raise an HTTP error
    else:
        user = login_manager.get_user(user_id, session)
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


async def is_logged_user(current_user: User = Depends(get_current_user)) -> bool:
    if not current_user.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Incorrect email or password",
        )
    return True


async def is_admin(current_user: User = Depends(get_current_user)) -> bool:
    if not current_user.can(Permission.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Incorrect email or password",
        )
    return True
