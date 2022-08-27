from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.auth import (
    Authenticator, basic_auth, get_current_user, login_manager
)
from src.app.dependencies import get_session
from src.app.pydantic.models.app import (
    LoginResponse, PydanticLimitedUser, PydanticUserMixin
)
from src.app.pydantic.models.common import BaseMsg

from src.database.models.app import User

router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
    tags=["auth"],
)


@router.get("/login", response_model=LoginResponse)
async def login(
        remember: bool = False,
        authenticator: Authenticator = Depends(login_manager),
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        session: AsyncSession = Depends(get_session),
):
    username = credentials.username
    password = credentials.password
    user = await authenticator.authenticate(session, username, password)
    token = authenticator.login(user, remember)
    return {
        "msg": "You are logged in",
        "data": {
            "user": user.to_dict(),
            "token": token,
        },
    }


@router.get("/logout", response_model=BaseMsg)
async def logout(
        authenticator: Authenticator = Depends(login_manager),
        current_user: PydanticUserMixin = Depends(get_current_user),
):
    if current_user.is_anonymous:
        return {"msg": "You were not logged in"}
    authenticator.logout()
    return {"msg": "Logged out"}


@router.get("/current_user", response_model=PydanticLimitedUser)
def get_current_user(
        current_user: PydanticUserMixin = Depends(get_current_user)
):
    return current_user.to_dict()


@router.post("/register")
async def register(
        registration_form,
        current_user: PydanticUserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.is_authenticated:
        return {"msg": "You cannot register, you are already logged in"}
    user = User(
        username=registration_form["username"],
        email=registration_form["email"],
        firstname=registration_form["firstname"],
        lastname=registration_form["lastname"],
        registration_datetime=datetime.now(),
    )
    user.set_password(registration_form["password"])
    session.add(user)
    await session.commit()
    return user.to_dict()

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