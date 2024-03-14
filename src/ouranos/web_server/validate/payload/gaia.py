from datetime import time
from enum import Enum
from typing import Optional, Type, TypeVar, Union

from pydantic import field_validator

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.validate.base import BaseModel


T = TypeVar("T", bound=Enum)


def safe_enum_or_none_from_name(
        enum: Type[T],
        name: Optional[Union[str, Enum]]
) -> Optional[T]:
    if name is not None:
        return safe_enum_from_name(enum, name)
    return None


class HardwareCreationPayload_NoEcoUid(BaseModel):
    name: str
    level: gv.HardwareLevel
    address: str
    type: gv.HardwareType
    model: str
    measures: Optional[list[str]] = None
    plants: Optional[list[str]] = None
    multiplexer_model: Optional[str] = None

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        return safe_enum_from_name(gv.HardwareLevel, value)

    @field_validator("type", mode="before")
    def parse_type(cls, value):
        return safe_enum_from_name(gv.HardwareType, value)


class HardwareCreationPayload(HardwareCreationPayload_NoEcoUid):
    ecosystem_uid: str


class HardwareUpdatePayload(BaseModel):
    ecosystem_uid: Optional[str] = None
    name: Optional[str] = None
    level: Optional[gv.HardwareLevel] = None
    address: Optional[str] = None
    type: Optional[gv.HardwareType] = None
    model: Optional[str] = None
    status: Optional[bool] = None
    measure: Optional[list[str]] = None
    plant_uid: Optional[list[str]] = None

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        return safe_enum_or_none_from_name(gv.HardwareLevel, value)

    @field_validator("type", mode="before")
    def parse_type(cls, value):
        return safe_enum_or_none_from_name(gv.HardwareType, value)
