from datetime import datetime, timezone

START_TIME = datetime.now(timezone.utc).replace(microsecond=0)

WEATHER_MEASURES = {
    "mean": ["temperature", "temperatureLow", "temperatureHigh", "humidity",
             "windSpeed", "cloudCover", "precipProbability", "dewPoint"],
    "mode": ["summary", "icon", "sunriseTime", "sunsetTime"],
    "other": ["time", "sunriseTime", "sunsetTime"],
    "range": ["temperature"],
}

WEATHER_DATA_MULTIPLICATION_FACTORS = {
    "temperature": 1,
    "humidity": 100,
    "windSpeed": 1,
    "cloudCover": 100,
    "precipProbability": 100,
}

HARDWARE_LEVELS = ["plants", "environment"]

HARDWARE_TYPE = ["sensor", "light", "heater", "cooler", "humidifier",
                 "dehumidifier"]

ACTUATORS_AVAILABLE = ["gpioDimmable", "gpioSwitch"]

PHYSICAL_SENSORS_AVAILABLE = ["DHT11", "DHT22", "VEML7700"]
VIRTUAL_SENSORS_AVAILABLE = [
    "virtualDHT11", "virtualDHT22", "virtualMega", "virtualMoisture",
    "virtualVEML7700"
]
SENSORS_AVAILABLE = PHYSICAL_SENSORS_AVAILABLE + VIRTUAL_SENSORS_AVAILABLE

HARDWARE_AVAILABLE = ACTUATORS_AVAILABLE + SENSORS_AVAILABLE
