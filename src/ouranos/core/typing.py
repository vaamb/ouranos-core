import typing as t

from ouranos.core.database.models.app import (
    CalendarEvent, CommunicationChannel, FlashMessage, GaiaJob,
    Role, Service, User
)
from ouranos.core.database.models.archives import (
    ArchiveActuatorHistory, ArchiveAppWarning, ArchiveHealthData,
    ArchiveSensorData
)
from ouranos.core.database.models.gaia import (
    ActuatorHistory, Ecosystem, Engine, EnvironmentParameter, GaiaWarning,
    Hardware, Health, Light, Management, Measure, Plant, SensorHistory
)
from ouranos.core.database.models.system import SystemHistory


ACTUATOR_MODE = t.Literal["on", "off", "automatic"]
ACTUATOR_TYPES = t.Literal["light", "heater", "cooler", "humidifier",
                           "dehumidifier"]
HARDWARE_LEVELS = t.Literal["plants", "environment", "all"]
HARDWARE_TYPES = t.Literal["sensor", "light", "heater", "cooler", "humidifier",
                           "dehumidifier", "all"]



__all__ = [
    "CalendarEvent", "CommunicationChannel", "FlashMessage", "GaiaJob",
    "Role", "Service", "User",
    "ArchiveActuatorHistory", "ArchiveAppWarning", "ArchiveHealthData",
    "ArchiveSensorData",
    "ActuatorHistory", "Ecosystem", "Engine", "EnvironmentParameter",
    "GaiaWarning", "Hardware", "Health", "Light", "Management", "Measure",
    "Plant", "SensorHistory",
    "SystemHistory",
    "HARDWARE_LEVELS", "HARDWARE_TYPES",
]
