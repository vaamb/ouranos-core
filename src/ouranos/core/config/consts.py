from datetime import datetime, timezone
from enum import Enum


class ImmutableDict(dict):
    def __setitem__(self, key, value):
        raise AttributeError


START_TIME = datetime.now(timezone.utc).replace(microsecond=0)

WEATHER_MEASURES = ImmutableDict({
    "mean": ["temperature", "temperatureLow", "temperatureHigh", "humidity",
             "windSpeed", "cloudCover", "precipProbability", "dewPoint"],
    "mode": ["summary", "icon", "sunriseTime", "sunsetTime"],
    "other": ["time", "sunriseTime", "sunsetTime"],
    "range": ["temperature"],
})

WEATHER_DATA_MULTIPLICATION_FACTORS = ImmutableDict({
    "temperature": 1,
    "humidity": 100,
    "windSpeed": 1,
    "cloudCover": 100,
    "precipProbability": 100,
})

ECOSYSTEM_TIMEOUT = 60

ACTUATORS_AVAILABLE = ["gpioDimmable", "gpioSwitch"]

PHYSICAL_SENSORS_AVAILABLE = ["DHT11", "DHT22", "VEML7700"]
VIRTUAL_SENSORS_AVAILABLE = [
    "virtualDHT11", "virtualDHT22", "virtualMega", "virtualMoisture",
    "virtualVEML7700"
]
SENSORS_AVAILABLE = PHYSICAL_SENSORS_AVAILABLE + VIRTUAL_SENSORS_AVAILABLE

HARDWARE_AVAILABLE = ACTUATORS_AVAILABLE + SENSORS_AVAILABLE


# File size
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024
MAX_PICTURE_FILE_SIZE = 10 * 1024 * 1024


# Login
SESSION_FRESHNESS = 15 * 60 * 60
SESSION_TOKEN_VALIDITY = 7 * 24 * 60 * 60

REGISTRATION_TOKEN_VALIDITY = 24 * 60 * 60


class TOKEN_SUBS(Enum):
    REGISTRATION: str = "registration"
    CAMERA_UPLOAD: str = "camera_upload"


class LOGIN_NAME(Enum):
    COOKIE: str = "session"
    HEADER: str = "Authorization"
