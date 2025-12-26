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


class HardwareUpdatePayload(BaseModel):
    name: str | MissingValue = missing
    active: bool | MissingValue = missing
    address: str | MissingValue = missing
    type: gv.HardwareType | MissingValue = missing
    level: gv.HardwareLevel | MissingValue = missing
    groups: set[str] | MissingValue = missing
    model: str | MissingValue = missing
    measures: list[str] | MissingValue = missing
    plants: list[str] | MissingValue = missing
    multiplexer_model: str | MissingValue = missing

    @field_validator("type", mode="before")
    @classmethod
    def parse_type(cls, value):
        if value == missing:
            return value
        if isinstance(value, int):
            return gv.HardwareType(value)
        return safe_enum_from_name(gv.HardwareType, value)

    @field_validator("level", mode="before")
    @classmethod
    def parse_level(cls, value):
        if value == missing:
            return value
        return safe_enum_from_name(gv.HardwareLevel, value)

    @field_validator("groups", mode="before")
    @classmethod
    def parse_groups(cls, value: str | list[str]):
        if value == missing:
            return value
        if isinstance(value, str):
            return {value}
        return set(value)

    @field_validator("measures", mode="before")
    @classmethod
    def parse_measures(cls, value: str | list[str] | list[dict[str, str | None]] | None):
        if value == missing:
            return value
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        rv = []
        for v in value:
            if isinstance(v, str):
                v_split = v.split("|")
                name = v_split[0]
                unit = v_split[1] if len(v_split) > 1 else None
                rv.append({"name": name, "unit": unit})
            else:
                rv.append(v)
        return rv

    @field_validator("plants", mode="before")
    @classmethod
    def parse_plants(cls, value: str | list[str] | None):
        if value == missing:
            return value
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
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
