from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Type, TypeVar

from pydantic import ConfigDict, field_serializer

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.validate.base import BaseModel


T = TypeVar("T", bound=Enum)


def safe_enum_or_none_from_name(
        enum: Type[T],
        name: str | Enum | None
) -> T | None:
    if name is not None:
        return safe_enum_from_name(enum, name)
    return None


class HardwareCreationPayload(gv.AnonymousHardwareConfig):
    ecosystem_uid: str


class HardwareUpdatePayload(HardwareCreationPayload):
    ecosystem_uid: str | None = None
    name: str | None = None
    level: gv.HardwareLevel | None = None
    address: str | None = None
    type: gv.HardwareType | None = None
    model: str | None = None
    status: bool | None = None
    measures: list[str] | None = None
    plant_uid: list[str] | None = None


class HardwareInfo(gv.HardwareConfig):
    ecosystem_uid: str
    last_log: datetime | None = None

    model_config = ConfigDict(
        extra="ignore",
    )

    @field_serializer("type")
    def serialize_type(self, type: gv.HardwareType, _info) -> str:
        return type.name


class HardwareModelInfo(BaseModel):
    model: str
    type: gv.HardwareType

    @field_serializer("type")
    def serialize_group(self, type: gv.HardwareType, _info):
        return type.name
