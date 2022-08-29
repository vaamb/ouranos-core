from pydantic import BaseModel


class BaseMsg(BaseModel):
    msg: str
