from __future__ import annotations

from pydantic import BaseModel


class logging_period(BaseModel):
    weather: int
    system: int
    sensors: int


class flash_message(BaseModel):
    level: int
    title: str
    description: str
