from flask import jsonify, request
from flask_login import login_user, logout_user, current_user
#from flask_jwt_extended import (create_access_token, create_refresh_token,
#                                jwt_required)
from flask_restx import Namespace, Resource

from src.app import db
from src.database.models.app import User


namespace = Namespace(
    "auth",
    description="Information about the system. Rem: it is required to be "
                "logged in to access data.",
)


@namespace.route("/login")
class Login(Resource):
    @namespace.doc(description="Login the user", security="basic_auth")
    def get(self):
        remember = request.args.get("remember", False)
        auth_header = request.authorization
        if auth_header:
            username = auth_header.username
            password = auth_header.password
            user = db.session.query(User).filter_by(username=username).first()
            if user is None or not user.check_password(password):
                return {"msg": "Wrong username or password"}, 401
            login_user(user, remember=remember)
            #access_token = create_access_token(
            #    identity=user,
            #    additional_claims={"perm": user.role.permissions}
            #)
            #refresh_token = create_refresh_token(identity=user)

            return {
                "msg": "You are logged in",
            #    "access_token": access_token,
            #    "refresh_token": refresh_token,
                "user": user.to_dict(),
            }
        return {"msg": "No credential received"}, 401


@namespace.route("/logout")
class Logout(Resource):
    def get(self):
        logout_user()
        return {"msg": "Logged out"}


@namespace.route("/register")
class Register(Resource):
    def post(self):
        pass


@namespace.route("/current_user")
class CurrentUser(Resource):
    def get(self):
        if current_user.is_authenticated:
            return current_user.to_dict()
        return {
            "username": "",
            "firstname": "",
            "lastname": "",
            "permissions": 0,
        }


"""
@namespace.route("/refresh")
class Token(Resource):
    @jwt_required(refresh=True)
    def get(self):
        token_type = request.args.get("token_type", "access")
        if token_type == "access":
            access_token = access_token = create_access_token(
                identity=current_user,
                additional_claims={"perm": current_user.role.permissions}
            )
            return jsonify(access_token=access_token)
        elif token_type == "refresh":
            refresh_token = create_refresh_token(identity=current_user)
            return jsonify(refresh_token=refresh_token)
        else:
            return {"msg": "Invalid 'token_type' argument. Must be 'access' "
                           "or 'refresh'"}, 400
"""
