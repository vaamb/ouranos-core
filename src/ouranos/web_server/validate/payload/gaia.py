from datetime import time
from enum import Enum
from typing import Optional, Union

from pydantic import field_validator

from gaia_validators import (
    ClimateParameter, HardwareLevel, HardwareType, LightMethod,
    safe_enum_from_name)

from ouranos.core.validate.base import BaseModel


def safe_enum_or_none_from_name(enum: Enum, name: Optional[Union[str, Enum]]):
    if name is not None:
        return safe_enum_from_name(enum, name)
    return None


class EcosystemCreationPayload(BaseModel):
    engine_uid: str
    name: str
    status: bool = False
    management: int = 0
    day_start: time = time(8, 00)
    night_start: time = time(20, 00)
    engine_uid: str


class EcosystemUpdatePayload(BaseModel):
    name: Optional[str] = None
    status: Optional[bool] = None
    management: Optional[int] = None
    day_start: Optional[time] = None
    night_start: Optional[time] = None
    engine_uid: Optional[str] = None


class EcosystemManagementUpdatePayload(BaseModel):
    sensors: Optional[bool] = None
    light: Optional[bool] = None
    climate: Optional[bool] = None
    watering: Optional[bool] = None
    health: Optional[bool] = None
    alarms: Optional[bool] = None
    webcam: Optional[bool] = None
    database: Optional[bool] = None


class EcosystemLightingUpdatePayload(BaseModel):
    method: LightMethod

    @field_validator("method", mode="before")
    def parse_method(cls, value):
        return safe_enum_from_name(LightMethod, value)


class EnvironmentParameterCreationPayload(BaseModel):
    parameter: ClimateParameter
    day: float
    night: float
    hysteresis: float = 0.0

    @field_validator("parameter", mode="before")
    def parse_parameter(cls, value):
        return safe_enum_from_name(ClimateParameter, value)


class EnvironmentParameterUpdatePayload(BaseModel):
    parameter: ClimateParameter
    day: Optional[float] = None
    night: Optional[float] = None
    hysteresis: Optional[float] = None

    @field_validator("parameter", mode="before")
    def parse_parameter(cls, value):
        return safe_enum_or_none_from_name(ClimateParameter, value)


class HardwareCreationPayload_NoEcoUid(BaseModel):
    name: str
    level: HardwareLevel
    address: str
    type: HardwareType
    model: str
    measures: Optional[list[str]] = None
    plants: Optional[list[str]] = None
    multiplexer_model: Optional[str] = None

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        return safe_enum_from_name(HardwareLevel, value)

    @field_validator("type", mode="before")
    def parse_type(cls, value):
        return safe_enum_from_name(HardwareType, value)


class HardwareCreationPayload(HardwareCreationPayload_NoEcoUid):
    ecosystem_uid: str


class HardwareUpdatePayload(BaseModel):
    ecosystem_uid: Optional[str] = None
    name: Optional[str] = None
    level: Optional[HardwareLevel] = None
    address: Optional[str] = None
    type: Optional[HardwareType] = None
    model: Optional[str] = None
    status: Optional[bool] = None
    measure: Optional[list[str]] = None
    plant_uid: Optional[list[str]] = None

    @field_validator("level", mode="before")
    def parse_level(cls, value):
        return safe_enum_or_none_from_name(HardwareLevel, value)

    @field_validator("type", mode="before")
    def parse_type(cls, value):
        return safe_enum_or_none_from_name(HardwareType, value)
