from pydantic import BaseModel


class Empty(BaseModel):
    pass


class PydanticSunTimes(BaseModel):
    sunrise: str
    sunset: str
    day_length: str


class PydanticCurrentWeather(BaseModel):
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


class PydanticHourlyWeather(PydanticCurrentWeather):
    apparentTemperature: float


class PydanticDailyWeather(BaseModel):
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
