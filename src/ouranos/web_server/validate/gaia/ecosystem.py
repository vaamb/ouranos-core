from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from pydantic import ConfigDict, Field, field_serializer, field_validator

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.database.models.gaia import Ecosystem, ActuatorState
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


# ---------------------------------------------------------------------------
#   Base ecosystem
# ---------------------------------------------------------------------------
class EcosystemCreationPayload(BaseModel):
    name: str
    status: bool = False
    management: int = 0
    nycthemeral_method: gv.NycthemeralSpanMethod = gv.NycthemeralSpanMethod.fixed
    nycthemeral_target: str | None = None
    day: time = time(8, 00)
    night: time = time(20, 00)
    lighting_method: gv.LightingMethod = gv.LightingMethod.fixed
    engine_uid: str

    @field_validator("nycthemeral_method", mode="before")
    def parse_nycthemeral_method(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.NycthemeralSpanMethod, value)
        return value

    @field_validator("lighting_method", mode="before")
    def parse_lighting_method(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.LightingMethod, value)
        return value

    @field_validator("day", "night", mode="before")
    def parse_time(cls, value):
        if isinstance(value, str):
            return time.fromisoformat(value)
        return value


class EcosystemBaseInfoUpdatePayload(BaseModel):
    name: str | None = None
    status: bool | None = None


EcosystemInfo = sqlalchemy_to_pydantic(
    Ecosystem,
    base=BaseModel,
    exclude=["management"],
    extra_fields={
        "management_value": (int, Field(validation_alias="management")),
        "connected": (bool, ...),
        "lighting_method": (Optional[gv.LightingMethod], ...),
    },
)


# ---------------------------------------------------------------------------
#   Ecosystem management
# ---------------------------------------------------------------------------
class EcosystemManagementUpdatePayload(BaseModel):
    sensors: bool | None = None
    light: bool | None = None
    climate: bool | None = None
    watering: bool | None = None
    health: bool | None = None
    alarms: bool | None = None
    pictures: bool | None = None
    database: bool | None = None


class ManagementInfo(BaseModel):
    name: str
    value: int


class _EcosystemManagementInfo(BaseModel):
    uid: str
    name: str
    switches: bool = False
    environment_data: bool = False
    plants_data: bool = False


class EcosystemManagementInfo(gv.ManagementConfig, _EcosystemManagementInfo):
    pass


# ---------------------------------------------------------------------------
#   Ecosystem lighting
# ---------------------------------------------------------------------------
class _EcosystemLightInfo(BaseModel):
    uid: str
    name: str
    span: gv.NycthemeralSpanMethod
    lighting: gv.LightingMethod = Field(validation_alias="method")
    target: str | None
    day: time | None
    night: time | None

    @field_serializer("span", "lighting")
    def serialize_enums(self, value):
        return value.name


class EcosystemLightInfo(gv.LightingHours, _EcosystemLightInfo):
    model_config = ConfigDict(
        extra="ignore",
    )


class NycthemeralCycleUpdatePayload(BaseModel):
    span: gv.NycthemeralSpanMethod | None = None
    lighting: gv.LightingMethod | None = None
    target: str | None = None
    day: time | None = None
    night: time | None = None

    @field_validator("span", mode="before")
    def parse_span(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.NycthemeralSpanMethod, value)
        return value

    @field_validator("lighting", mode="before")
    def parse_lighting(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.LightingMethod, value)
        return value

    @field_validator("day", "night", mode="before")
    def parse_time(cls, value):
        if isinstance(value, str):
            return time.fromisoformat(value)
        return value


# ---------------------------------------------------------------------------
#   Ecosystem climate parameter
# ---------------------------------------------------------------------------
class EnvironmentParameterCreationPayload(gv.ClimateConfig):
    model_config = ConfigDict(
        extra="ignore",
    )


class EnvironmentParameterUpdatePayload(BaseModel):
    day: float | None = None
    night: float | None = None
    hysteresis: float | None = None


class EnvironmentParameterInfo(BaseModel):
    uid: str
    name: str
    environment_parameters: list[EnvironmentParameterCreationPayload]


# ---------------------------------------------------------------------------
#   Ecosystem actuators
# ---------------------------------------------------------------------------
_ActuatorStateInfo = sqlalchemy_to_pydantic(
    ActuatorState,
    base=BaseModel,
    exclude=["ecosystem_uid"],
    extra_fields={
        "level": (Optional[float], ...),
    },
)


class ActuatorStateInfo(_ActuatorStateInfo):
    @field_serializer("type")
    def serialize_type(self, value):
        return value.name


class EcosystemActuatorInfo(BaseModel):
    uid: str
    name: str
    actuators_state: list[ActuatorStateInfo]


class EcosystemActuatorRecords(BaseModel):
    uid: str
    name: str
    actuator_type: gv.HardwareType
    span: tuple[datetime, datetime]
    values: list[tuple[datetime, bool, gv.ActuatorMode, bool, float | None]]
    order: tuple[str, str, str, str, str] = (
        "timestamp", "active", "mode", "status", "level")

    @field_serializer("actuator_type")
    def serialize_actuator_type(self, value):
        return value.name


class EcosystemTurnActuatorPayload(BaseModel):
    mode: gv.ActuatorModePayload = gv.ActuatorModePayload.automatic
    countdown: float = 0.0

    @field_validator("mode", mode="before")
    def parse_mode(cls, value):
        if isinstance(value, str):
            return safe_enum_from_name(gv.ActuatorModePayload, value)
        return value
