from ouranos.core.validate.base import BaseModel


class LoggingPeriodResponse(BaseModel):
    weather: int
    system: int
    sensors: int


class FlashMessageResponse(BaseModel):
    level: int
    title: str
    description: str
