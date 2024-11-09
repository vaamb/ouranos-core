from datetime import datetime

from pydantic import field_validator

from ouranos.core.validate.base import BaseModel


class CurrentWeatherInfo(BaseModel):
    timestamp: datetime
    temperature: float
    humidity: float
    dew_point: float
    wind_speed: float
    cloud_cover: float | None
    summary: str | None
    icon: str | None

    @field_validator("timestamp", mode="before")
    def parse_timestamp(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value


class HourlyWeatherInfo(CurrentWeatherInfo):
    precipitation_probability: float


class DailyWeatherInfo(HourlyWeatherInfo):
    temperature_min: float
    temperature_max: float
