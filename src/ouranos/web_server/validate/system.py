from datetime import datetime
from typing import Optional

from ouranos.core.validate.base import BaseModel


class SystemInfo(BaseModel):
    uid: str
    start_time: datetime
    RAM_total: float
    DISK_total: float


class SystemData(BaseModel):
    values: list[
        tuple[datetime, str, float, Optional[float], float, float, float]
    ]
    order: tuple[
        str, str, str, str, str, str, str, str, str,
    ] = (
        "timestamp", "system_uid", "CPU_used", "CPU_temp", "RAM_process",
        "RAM_used", "DISK_used",
    )
    totals: dict
