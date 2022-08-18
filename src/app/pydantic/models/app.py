from pydantic import BaseModel
from pydantic_sqlalchemy import sqlalchemy_to_pydantic

from src.database.models.app import User


class PydanticLimitedUser(BaseModel):
    username: str
    firstname: str
    lastname: str
    permissions: int


PydanticUser = sqlalchemy_to_pydantic(User)

