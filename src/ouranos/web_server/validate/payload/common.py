from __future__ import annotations

from ouranos.core.validate.base import BaseModel
from ouranos.core.database.models.common import ImportanceLevel


class WarningCreationPayload(BaseModel):
    level: ImportanceLevel
    title: str
    description: str


class WarningUpdatePayload(BaseModel):
    level: ImportanceLevel | None = None
    title: str | None = None
    description: str | None = None
