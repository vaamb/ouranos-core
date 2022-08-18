from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasicCredentials

from src.app.auth import (
    LoginManager, basic_auth, get_login_manager, get_current_user
)
from src.app.pydantic.models.app import PydanticLimitedUser, PydanticUser


router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
    tags=["auth"],
)


@router.get("/login")
async def login(
        login_manager: LoginManager = Depends(get_login_manager),
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        remember: bool = False
):
    username = credentials.username
    password = credentials.password
    user = login_manager.authenticate(username, password)
    login_manager.login(user, remember)
    return {
        "msg": "You are logged in",
        "user": user.to_dict(),
    }


@router.get("/logout")
async def logout(
        login_manager: LoginManager = Depends(get_login_manager),
        current_user: PydanticUser = Depends(get_current_user)
):
    login_manager.logout()
    return {"msg": "Logged out"}


@router.get("/current_user", response_model=PydanticLimitedUser)
def get_current_user(current_user: PydanticUser = Depends(get_current_user)):
    return current_user.to_dict()


"""
@namespace.route("/register")
class Register(Resource):
    def post(self):
        pass


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
