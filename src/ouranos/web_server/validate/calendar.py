from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.validate.base import BaseModel


class EventCreationPayload(BaseModel):
    level: gv.WarningLevel = gv.WarningLevel.low
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.WarningLevel, value)
        return value

    @field_validator("start_time", "end_time", mode="before")
    def parse_datetime(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value


class EventUpdatePayload(BaseModel):
    level: gv.WarningLevel | None = None
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.WarningLevel, value)
        return value

    @field_validator("start_time", "end_time", mode="before")
    def parse_datetime(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value


class EventInfo(BaseModel):
    id: int
    level: gv.WarningLevel
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
