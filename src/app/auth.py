import pickle

from flask import current_app
from flask_login import AnonymousUserMixin
import jwt

from . import db, login_manager
from .models import User


class AnonymousUser(AnonymousUserMixin):
    def can(self, perm):
        return False


login_manager.anonymous_user = AnonymousUser
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    return get_user(user_id)


@login_manager.request_loader
def load_user(request):
    auth = request.headers.get("Authorization")
    if auth:
        auth_type, token = request.headers["Authorization"].split(None, 1)
        if auth_type.lower() not in ("bearer", "token"):
            return None
    else:
        token = request.args.get("token")
    if token:
        user_id = decode_user_id_token(token)
        if user_id:
            return get_user(user_id)
    return None


def get_user(user_id: int) -> User:
    # TODO: can cache user on redis, memcache ... from here
    return db.session.query(User).get(int(user_id))


def create_user_id_token(user_id: int):
    payload = {"user_id": user_id}
    return jwt.encode(payload, key=current_app.config["JWT_SECRET_KEY"], algorithm="HS256")


def decode_user_id_token(token) -> int:
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET_KEY"],
                             algorithms=["HS256"])
        return payload.get("user_id", 0)
    except jwt.PyJWTError:  # Invalid/expired token
        return 0
