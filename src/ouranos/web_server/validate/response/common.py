from datetime import datetime
from typing import Optional

from ouranos.core.database.models.common import WarningLevel
from ouranos.core.validate.base import BaseModel


class WarningResult(BaseModel):
    id: int
    level: WarningLevel
    title: str
    description: str
    created_on: datetime
    solved_on: Optional[datetime]
