from __future__ import annotations

from datetime import datetime

import gaia_validators as gv

from ouranos.core.validate.base import BaseModel


class EventCreationPayload(BaseModel):
    level: gv.WarningLevel = gv.WarningLevel.low
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime


class EventUpdatePayload(BaseModel):
    level: gv.WarningLevel | None = None
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class EventInfo(BaseModel):
    id: int
    level: gv.WarningLevel
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
