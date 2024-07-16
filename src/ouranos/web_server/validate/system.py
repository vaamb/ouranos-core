from datetime import datetime
from typing import Optional
from typing_extensions import TypedDict

from pydantic import Field

from ouranos.core.validate.base import BaseModel


class SystemInfo(BaseModel):
    system_uid: str = Field(validation_alias="uid")
    start_time: datetime
    RAM_total: float
    DISK_total: float


class SystemTotals(TypedDict):
    RAM_total: float
    DISK_total: float


class SystemData(BaseModel):
    system_uid: str = Field(validation_alias="uid")
    span: tuple[datetime, datetime]
    values: list[
        tuple[datetime, float, Optional[float], float, float, float]
    ]
    order: tuple[str, str, str, str, str, str] = (
        "timestamp", "CPU_used", "CPU_temp", "RAM_process", "RAM_used",
        "DISK_used",
    )
    totals: SystemTotals
