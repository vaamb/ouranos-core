import typing as t

from pydantic import BaseModel
from pydantic_sqlalchemy import sqlalchemy_to_pydantic

from src.database.models.app import User


class PydanticLimitedUser(BaseModel):
    username: str
    firstname: str
    lastname: str
    permissions: int


class PydanticUserMixin(BaseModel):
    is_authenticated: bool
    is_anonymous: bool
    get_id: t.Optional[int]
    can: bool

    def to_dict(self) -> dict:
        pass


PydanticUser = sqlalchemy_to_pydantic(User)

