from ouranos.core.validate.base import BaseModel
from ouranos.core.database.models.common import WarningLevel


class WarningPayload(BaseModel):
    level: WarningLevel
    title: str
    description: str
