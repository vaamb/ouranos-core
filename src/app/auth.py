import typing as t
from hashlib import sha512

from fastapi import Request, Response, Depends
from fastapi.security.http import HTTPBasic, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
import jwt

from . import db
from src.database.models.app import anonymous_user, User, UserMixin
from config import Config


class HTTPCookieBearer(HTTPBearer):
    async def __call__(self, request: Request) -> t.Optional[str]:
        authorization_cookie: str = request.cookies.get("Authorization")
        authorization_header: str = request.headers.get("Authorization")
        for authorization in (authorization_cookie, authorization_header):
            if not authorization:
                break
            scheme, param = get_authorization_scheme_param(authorization)
            if scheme.lower() == "bearer":
                return param
        return None


basic_auth = HTTPBasic()
cookie_bearer_auth = HTTPCookieBearer()


def encode_payload(
        payload: dict,
        key: str = None,
        algorithm: str = "HS256",
) -> str:
    if not key:
        key = Config.SECRET_KEY
    return jwt.encode(payload, key, algorithm)


def decode_token(
        token: str,
        key: str = None,
        algorithm: str = "HS256",
) -> dict:
    return jwt.decode(token, key, algorithm)


def create_session_id(remote_address, user_agent):
    base = f"{remote_address}|{user_agent}"
    h = sha512()
    h.update(base.encode("utf8"))
    return h.hexdigest()


def authenticate_user(db_session, username: str, password: str):
    #TODO
    pass


def login_user(  # TODO: replace cleaner
        user: User,
        remember: bool,
        request: Request,
        response: Response,
) -> None:
    remote_address = request.client.host
    user_agent = request.headers.get("user-agent")
    session_id = create_session_id(remote_address, user_agent)
    # TODO: use remember
    session = {
        "id": session_id,
        "user_id": user.id,
    }
    token = encode_payload(session)
    response.set_cookie("Authorization", f"Bearer {token}", httponly=True)


def logout_user(response: Response) -> None:
    response.delete_cookie("Authorization")


# TODO: use async
def get_user(user_id: int) -> User:
    return db.session.query(User).filter_by(id=user_id).one_or_none()


async def _get_current_user(token: str = Depends(cookie_bearer_auth)) -> UserMixin:
    if not token:
        return anonymous_user
    try:
        payload = decode_token(token)
        user_id = payload.get("user_id", None)
    except jwt.PyJWTError:
        return anonymous_user
    user = get_user(user_id)
    if user:
        return user
    return anonymous_user


async def get_current_user(user: UserMixin = Depends(_get_current_user)) -> UserMixin:
    return user
