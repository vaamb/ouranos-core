from typing import Union

from flask import request
from flask_login import login_user, logout_user, current_user
from flask_restx import Namespace, Resource

from src.app import db
from src.models import User
from .decorators import login_required
from src.app.auth import create_auth_token


namespace = Namespace(
    "system",
    description="Information about the system. Rem: it is required to be "
                "logged in to access data.",
)


def arg_to_bool(arg: Union[bool, int, str]) -> bool:
    if isinstance(arg, bool):
        return arg
    if isinstance(arg, int):
        return bool(arg)
    if arg.lower() == "true":
        return True
    elif arg.lower() == "false":
        return False
    raise ValueError("string must be 1, 0, 'true' or 'false'")


@namespace.route("/login")
class Login(Resource):
    def get(self):
        remember = request.args.get("remember", False)
        return_token = arg_to_bool(request.args.get("remember", False))
        auth = request.authorization
        if auth:  # or "Authorization" in request.headers:
            # TODO: process other type of Authorization in header
            #  (val others than Basic or Digest)
            username = auth.username
            password = auth.password
            user = db.session.query(User).filter_by(username=username).first()
            if user is None or not user.check_password(password):
                return {"error": "Wrong username or password"}, 401
            # TODO: return token? if request not from browser
            login_user(user, remember=remember)
            rv = {"success": f"You are now logged in"}
            if return_token:
                # TODO: use the one from user model
                rv.update({"token": create_auth_token(user)})
            return rv


@namespace.route("/logout")
class Logout(Resource):
    def get(self):
        logout_user()


@namespace.route("/token")
class Token(Resource):
    @login_required
    def get(self):
        if current_user.is_authenticated:  # should be always true
            return {"token": create_auth_token(current_user)}
