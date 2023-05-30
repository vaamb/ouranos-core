from __future__ import annotations

from pydantic import BaseModel

from ouranos.core.database.models import WarningLevel


class BaseResponse(BaseModel):
    msg: str


class message_creation(BaseModel):
    level: WarningLevel = WarningLevel.low
    title: str
    description: str | None = None
