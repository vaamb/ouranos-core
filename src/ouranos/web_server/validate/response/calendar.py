from __future__ import annotations

from datetime import datetime

from ouranos.core.database.models.common import ImportanceLevel
from ouranos.core.validate.base import BaseModel


class EventResult(BaseModel):
    id: int
    level: ImportanceLevel
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
