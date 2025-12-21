from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Type, TypeVar

from pydantic import ConfigDict, field_serializer, field_validator

import gaia_validators as gv
from gaia_validators import MissingValue, missing, safe_enum_from_name

from ouranos.core.validate.base import BaseModel
from ouranos.core.database.models.gaia import HardwareGroup


T = TypeVar("T", bound=Enum)


def safe_enum_or_none_from_name(
        enum: Type[T],
        name: str | Enum | None
) -> T | None:
    if name is not None:
        return safe_enum_from_name(enum, name)
    return None


class HardwareType(BaseModel):
    name: str
    value: int


class HardwareUpdatePayload(gv.AnonymousHardwareConfig):
    model_config = ConfigDict(
        extra="ignore",
    )

    name: str | MissingValue = missing
    active: bool | MissingValue = missing
    level: gv.HardwareLevel | MissingValue = missing
    address: str | MissingValue = missing
    type: gv.HardwareType | MissingValue = missing
    model: str | MissingValue = missing
    status: bool | MissingValue = missing
    measures: list[str] | MissingValue = missing
    plant_uid: list[str] | MissingValue = missing

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.HardwareLevel, value)
        return value

    @field_validator("type", mode="before")
    def parse_type(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.HardwareType, value)
        return value


class PlantSummary(BaseModel):
    uid: str
    name: str


class _HardwareInfo(BaseModel):
    uid: str


class HardwareInfo(gv.AnonymousHardwareConfig, _HardwareInfo):
    model_config = ConfigDict(
        extra="ignore",
    )

    ecosystem_uid: str
    last_log: datetime | None = None
    plants: list[PlantSummary]

    @field_validator("groups", mode="before")
    def parse_groups(cls, value: list[HardwareGroup]):
        if isinstance(value, list):
            return {group.name for group in value}
        return value

    @field_serializer("type")
    def serialize_type(self, value: gv.HardwareType, _info) -> str:
        return value.name


class HardwareModelInfo(BaseModel):
    model: str
    type: gv.HardwareType

    @field_serializer("type")
    def serialize_type(self, value: gv.HardwareType, _info):
        return value.name
