from __future__ import annotations

from datetime import datetime

from ouranos.core.database.models.common import ImportanceLevel
from ouranos.core.validate.base import BaseModel


class EventCreationPayload(BaseModel):
    level: ImportanceLevel = ImportanceLevel.low
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime


class EventUpdatePayload(BaseModel):
    level: ImportanceLevel | None = None
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class EventInfo(BaseModel):
    id: int
    level: ImportanceLevel
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
