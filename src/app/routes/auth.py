from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBasicCredentials

from src.app import db
from src.app.auth import basic_auth, get_current_user, login_user, logout_user

from pydantic import BaseModel


class User(BaseModel):
    def to_dict(self) -> dict:
        pass


router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
    tags=["auth"],
)


@router.get("/login")
def login(
        request: Request,
        response: Response,
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        remember: bool = False
):
    username = credentials.username
    password = credentials.password
    user = db.session.query(User).filter_by(username=username).first()

    if user is None or not user.check_password(password):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    login_user(user, remember, request, response)
    #access_token = create_access_token(
    #    identity=user,
    #    additional_claims={"perm": user.role.permissions}
    #)
    #refresh_token = create_refresh_token(identity=user)
    # TODO: close session after requests
    return {
        "msg": "You are logged in",
    #    "access_token": access_token,
    #    "refresh_token": refresh_token,
        "user": user.to_dict(),
    }


@router.get("/logout")
def logout(response: Response, current_user: User = Depends(get_current_user)):
    logout_user(response)
    return {"msg": "Logged out"}


@router.get("/current_user")
def get_current_user(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()


"""
@namespace.route("/register")
class Register(Resource):
    def post(self):
        pass




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
