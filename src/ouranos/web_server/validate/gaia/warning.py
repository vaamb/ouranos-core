from __future__ import annotations

from datetime import datetime

import gaia_validators as gv

from ouranos.core.validate.base import BaseModel


class WarningInfo(BaseModel):
    id: int
    level: gv.WarningLevel
    title: str
    description: str
    created_on: datetime
    created_by: str
    updated_on: datetime | None
    seen_on: datetime | None
    solved_on: datetime | None
