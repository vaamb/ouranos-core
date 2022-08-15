from hashlib import sha512

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.app import db
from src.database.models.app import User
import jwt

security = HTTPBasic()


router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
    tags=["auth"],
)


def _create_session_id(remote_address, user_agent):
    base = f"{remote_address}|{user_agent}"
    h = sha512()
    h.update(base.encode("utf8"))
    return h.hexdigest()


@router.get("/login")
def login(
        request: Request,
        credentials: HTTPBasicCredentials = Depends(security),
        remember: bool = False
):
    username = credentials.username
    password = credentials.password
    with db.scoped_session() as session:
        user = session.query(User).filter_by(username=username).first()
    print(username)

    if user is None or not user.check_password(password):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    # TODO: use remember
    remote_address = request.client.host
    user_agent = request.headers.get("user-agent")

    session = {
        "id": _create_session_id(remote_address, user_agent),
        "user_id": user.id,
    }

    #login_user(user, remember=remember)
    #access_token = create_access_token(
    #    identity=user,
    #    additional_claims={"perm": user.role.permissions}
    #)
    #refresh_token = create_refresh_token(identity=user)
    print(credentials)
    return {
        "msg": "You are logged in",
    #    "access_token": access_token,
    #    "refresh_token": refresh_token,
    #    "user": user.to_dict(),
    }

"""
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
