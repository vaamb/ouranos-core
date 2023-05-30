from ouranos.core.database.models.app import Service
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


class LoggingPeriodResponse(BaseModel):
    weather: int
    system: int
    sensors: int


class FlashMessageResponse(BaseModel):
    level: int
    title: str
    description: str


ServiceInfo = sqlalchemy_to_pydantic(
    Service,
    base=BaseModel,
    exclude=["id"]
)
