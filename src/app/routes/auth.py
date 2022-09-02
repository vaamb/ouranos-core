from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.security import HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.exceptions import DuplicatedEntry
from src.app.auth import (
    Authenticator, basic_auth, get_current_user, login_manager
)

from src.app.dependencies import get_session
from src.core import api
from src.core.pydantic.models.app import (
    LoginResponse, PydanticLimitedUser, PydanticUserMixin
)
from src.core.pydantic.models.common import BaseMsg
from src.core.utils import ExpiredTokenError, InvalidTokenError, Tokenizer


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


def check_invitation_token(invitation_token: str) -> dict:
    try:
        payload = Tokenizer.loads(invitation_token)
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expired token"
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid token"
        )
    else:
        return payload


@router.post("/register")
async def register_new_user(
        registration_payload: dict = Body(),
        invitation_token: str = Query(),
        current_user: PydanticUserMixin = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
):
    if current_user.is_authenticated:
        return {"msg": "You cannot register, you are already logged in"}
    check_invitation_token(invitation_token)
    try:
        user = await api.admin.create_user(session, **registration_payload)
    except DuplicatedEntry as e:
        args = e.args[0]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=args
        )
    else:
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