from hashlib import sha512
import typing as t

import jwt

from . import db
from src.database.models.app import User
from config import Config


if t.TYPE_CHECKING:
    from fastapi import Request, Response


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


def login_user(
        user: User,
        remember: bool,
        request,
        response,
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
    response.set_cookie("session", token)


def get_user(user_id: int) -> User:
    return db.session.query(User).filter_by(id=user_id).one_or_none()
