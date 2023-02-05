from pydantic import BaseModel


class sun_times(BaseModel):
    sunrise: str
    sunset: str
    day_length: str


class current_weather(BaseModel):
    time: int
    summary: str
    icon: str
    precipIntensity: int
    precipProbability: int
    temperature: float
    apparentTemperature: float
    dewPoint: float
    humidity: float
    pressure: float
    windSpeed: float
    windGust: float
    windBearing: int
    cloudCover: float
    uvIndex: int
    visibility: float
    ozone: float


class hourly_weather(current_weather):
    apparentTemperature: float


class daily_weather(BaseModel):
    time: int
    summary: str
    icon: str
    sunriseTime: int
    sunsetTime: int
    moonPhase: float
    precipIntensity: int
    precipIntensityMax: int
    precipProbability: int
    temperatureHigh: float
    temperatureHighTime: int
    temperatureLow: float
    temperatureLowTime: int
    apparentTemperatureHigh: float
    apparentTemperatureHighTime: int
    apparentTemperatureLow: float
    apparentTemperatureLowTime: int
    dewPoint: float
    humidity: float
    pressure: float
    windSpeed: float
    windGust: float
    windBearing: int
    cloudCover: float
    uvIndex: int
    uvIndexTime: int
    visibility: float
    ozone: float
    temperatureMin: float
    temperatureMinTime: int
    temperatureMax: float
    temperatureMaxTime: int
    apparentTemperatureMin: float
    apparentTemperatureMinTime: int
    apparentTemperatureMax: float
    apparentTemperatureMaxTime: int
