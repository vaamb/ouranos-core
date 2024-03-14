from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Type, TypeVar

from pydantic import field_validator, field_serializer

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.database.models.gaia import Plant
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


T = TypeVar("T", bound=Enum)


def safe_enum_or_none_from_name(
        enum: Type[T],
        name: str | Enum | None
) -> T | None:
    if name is not None:
        return safe_enum_from_name(enum, name)
    return None


class HardwareCreationPayload_NoEcoUid(BaseModel):
    name: str
    level: gv.HardwareLevel
    address: str
    type: gv.HardwareType
    model: str
    measures: list[str] | None = None
    plants: list[str] | None = None
    multiplexer_model: str | None = None

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        return safe_enum_from_name(gv.HardwareLevel, value)

    @field_validator("type", mode="before")
    def parse_type(cls, value):
        return safe_enum_from_name(gv.HardwareType, value)


class HardwareCreationPayload(HardwareCreationPayload_NoEcoUid):
    ecosystem_uid: str


class HardwareUpdatePayload(BaseModel):
    ecosystem_uid: str | None = None
    name: str | None = None
    level: gv.HardwareLevel | None = None
    address: str | None = None
    type: gv.HardwareType | None = None
    model: str | None = None
    status: bool | None = None
    measure: list[str] | None = None
    plant_uid: list[str] | None = None

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        return safe_enum_or_none_from_name(gv.HardwareLevel, value)

    @field_validator("type", mode="before")
    def parse_type(cls, value):
        return safe_enum_or_none_from_name(gv.HardwareType, value)


class MeasureInfo(BaseModel):
    name: str
    unit: str | None


PlantInfo = sqlalchemy_to_pydantic(
    Plant,
    base=BaseModel
)


class HardwareInfo(BaseModel):
    uid: str
    ecosystem_uid: str
    name: str
    level: gv.HardwareLevel
    address: str
    type: gv.HardwareType
    model: str
    last_log: datetime | None = None
    measures: list[MeasureInfo]
    plants: list[PlantInfo]

    @field_serializer("type")
    def serialize_group(self, type: gv.HardwareType, _info):
        return type.name


class HardwareModelInfo(BaseModel):
    model: str
    type: gv.HardwareType

    @field_serializer("type")
    def serialize_group(self, type: gv.HardwareType, _info):
        return type.name
