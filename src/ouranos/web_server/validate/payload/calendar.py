from __future__ import annotations

from datetime import datetime
from typing import Optional

from ouranos.core.validate.base import BaseModel
from ouranos.core.database.models.common import ImportanceLevel


class EventCreationPayload(BaseModel):
    level: ImportanceLevel = ImportanceLevel.low
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime


class EventUpdatePayload(BaseModel):
    level: Optional[ImportanceLevel] = None
    title: Optional[str] = None
    description: str | None = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

