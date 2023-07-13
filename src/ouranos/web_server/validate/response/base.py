from enum import Enum

from pydantic import field_validator

from ouranos.core.validate.base import BaseModel


class ResultStatus(Enum):
    failure = 0
    success = 1


class BaseResponse(BaseModel):
    msg: str


class ResultResponse(BaseResponse):
    msg: str
    status: ResultStatus

    @field_validator("status", mode="before")
    def parse_status(cls, value):
        if isinstance(value, Enum):
            return value
        return {i.name: i for i in Enum}[value]
