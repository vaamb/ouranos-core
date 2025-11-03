from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from pydantic import ConfigDict, Field, field_serializer, field_validator

import gaia_validators as gv
from gaia_validators import MissingValue, missing, safe_enum_from_name

from ouranos.core.database.models.gaia import (
    ActuatorState, Ecosystem, EnvironmentParameter, HardwareGroup, Measure)
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
    name: str | MissingValue = missing
    status: bool | MissingValue = missing


EcosystemInfo = sqlalchemy_to_pydantic(
    Ecosystem,
    base=BaseModel,
    exclude=["management"],
    extra_fields={
        "management_value": (int, Field(validation_alias="management")),
        "connected": (bool, ...),
        #"lighting_method": (Optional[gv.LightingMethod], ...),
    },
)


# ---------------------------------------------------------------------------
#   Ecosystem management
# ---------------------------------------------------------------------------
class EcosystemManagementUpdatePayload(BaseModel):
    sensors: bool | MissingValue = missing
    light: bool | MissingValue = missing
    climate: bool | MissingValue = missing
    watering: bool | MissingValue = missing
    health: bool | MissingValue = missing
    alarms: bool | MissingValue = missing
    pictures: bool | MissingValue = missing
    database: bool | MissingValue = missing


class ManagementInfo(BaseModel):
    name: str
    value: int


class _EcosystemManagementInfo(BaseModel):
    uid: str
    name: str
    actuators: bool = False
    ecosystem_data: bool = False
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
    span: gv.NycthemeralSpanMethod | MissingValue = missing
    lighting: gv.LightingMethod | MissingValue = missing
    target: str | None | MissingValue = missing
    day: time | MissingValue = missing
    night: time | MissingValue = missing

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
#   Ecosystem environment parameter
# ---------------------------------------------------------------------------
class EnvironmentParameterCreationPayload(gv.ClimateConfig):
    model_config = ConfigDict(
        extra="ignore",
    )


class EnvironmentParameterUpdatePayload(BaseModel):
    day: float | MissingValue = missing
    night: float | MissingValue = missing
    hysteresis: float | MissingValue = missing
    alarm: float | None | MissingValue = missing


_EnvironmentParameterInfo = sqlalchemy_to_pydantic(
    EnvironmentParameter,
    base=BaseModel,
    exclude=[
        "alarm",
        "ecosystem_uid",
        "linked_actuator_group_decrease_id",
        "linked_actuator_group_increase_id",
        "linked_measure_id",
    ],
    extra_fields={
        "alarm": (Optional[float], ...),
        "uid": (str, Field(validation_alias="ecosystem_uid")),
        "linked_actuator_group_increase": (Optional[str], ...),
        "linked_actuator_group_decrease": (Optional[str], ...),
        "linked_measure": (Optional[str], ...),
    },
)


class EnvironmentParameterInfo(_EnvironmentParameterInfo):
    @field_validator(
        "linked_actuator_group_increase", "linked_actuator_group_decrease",
        mode="before"
    )
    def parse_actuator_group(cls, value):
        if isinstance(value, HardwareGroup):
            return value.name
        return value

    @field_validator("linked_measure", mode="before")
    def parse_measure(cls, value):
        if isinstance(value, Measure):
            return value.name
        return value


class EcosystemEnvironmentParametersInfo(BaseModel):
    uid: str
    name: str
    environment_parameters: list[EnvironmentParameterInfo]


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
