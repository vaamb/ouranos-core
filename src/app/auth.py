from flask import current_app
from flask_login import AnonymousUserMixin
import jwt

from . import db, login_manager
from src.models import User
from src.utils import ExpiredTokenError, InvalidTokenError, Tokenizer


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
        try:
            payload = check_auth_token(token)
            if payload.get("use") != "auth":
                return None
            user_id = payload.get["user_id"]
            return get_user(user_id)
        except (ExpiredTokenError, InvalidTokenError):
            return None
    return None


def get_user(user_id: int) -> User:
    # TODO: can cache user on redis, memcache ... from here
    return db.session.query(User).get(int(user_id))


def create_auth_token(user: User,
                      expires_in: int = None,
                      secret_key: str = None
                      ) -> str:
    return user.create_token("auth", expires_in=expires_in,
                             secret_key=secret_key)


def check_auth_token(token: str,
                     secret_key: str = current_app.config["SECRET_KEY"]
                     ) -> dict:
    payload = Tokenizer.loads(secret_key, token)
    if payload.get("use") != "auth":
        raise InvalidTokenError
    return payload
