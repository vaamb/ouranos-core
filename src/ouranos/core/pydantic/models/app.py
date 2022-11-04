import typing as t

from pydantic import BaseModel, create_model
from pydantic_sqlalchemy import sqlalchemy_to_pydantic

from ouranos.core.database.models.app import User


class PydanticLimitedUser(BaseModel):
    username: t.Optional[str]
    firstname: t.Optional[str]
    lastname: t.Optional[str]
    permissions: int


class LoginResponse(BaseModel):
    msg: str
    data: create_model("tr", user=(dict, PydanticLimitedUser))


class PydanticUserMixin(BaseModel):
    is_authenticated: bool
    is_anonymous: bool
    get_id: t.Optional[int]
    can: bool

    def to_dict(self) -> dict:
        pass


PydanticUser = sqlalchemy_to_pydantic(User)

