from __future__ import annotations

from ouranos.core.validate.base import BaseModel
from ouranos.core.database.models.common import WarningLevel


class WarningCreationPayload(BaseModel):
    level: WarningLevel
    title: str
    description: str


class WarningUpdatePayload(BaseModel):
    level: WarningLevel | None = None
    title: str | None = None
    description: str | None = None
