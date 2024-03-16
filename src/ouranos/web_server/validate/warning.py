from __future__ import annotations

from datetime import datetime

from ouranos.core.database.models.common import ImportanceLevel
from ouranos.core.validate.base import BaseModel


class WarningInfo(BaseModel):
    id: int
    level: ImportanceLevel
    title: str
    description: str
    created_on: datetime
    solved_on: datetime | None
