from enum import Enum

from pydantic import validator

from gaia_validators import  HardwareType, safe_enum_from_name

from ouranos.core.validate.base import BaseModel


class ActuatorModePayload(Enum):
    on = "on"
    off = "off"
    automatic = "automatic"


class ActuatorTurnToPayload(BaseModel):
    actuator: HardwareType
    mode: ActuatorModePayload
    countdown: float = 0.0

    @validator("actuator", pre=True)
    def parse_actuator(cls, value):
        if isinstance(value, Enum):
            return value
        return safe_enum_from_name(HardwareType, value)

    @validator("mode", pre=True)
    def parse_mode(cls, value):
        if isinstance(value, Enum):
            return value
        return safe_enum_from_name(ActuatorModePayload, value)
