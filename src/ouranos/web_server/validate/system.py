from datetime import datetime
from typing import Optional

from ouranos.core.validate.base import BaseModel


class SystemRecordResponse(BaseModel):
    values: list[
        tuple[datetime, str, float, Optional[float], float, float, float,
              float, float]
    ]
    order: tuple[str, str, str, str, str, str, str, str, str]
