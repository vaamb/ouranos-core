from fastapi import APIRouter
from fastapi.security import HTTPBasicCredentials

from src.app import db
from src.database.models.app import User


router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
    tags=["auth"],
)


@router.get("/login")
def login(credentials: HTTPBasicCredentials, remember: bool = False):
    username = credentials.username
    password = credentials.password
    user = db.session.query(User).filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return {"msg": "Wrong username or password"}, 401
    #login_user(user, remember=remember)
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
