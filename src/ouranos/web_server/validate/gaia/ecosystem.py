from __future__ import annotations

from datetime import time
from typing import Optional

from pydantic import Field, field_validator

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.database.models.gaia import Ecosystem, EnvironmentParameter
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


# ---------------------------------------------------------------------------
#   Base ecosystem
# ---------------------------------------------------------------------------
class EcosystemCreationPayload(BaseModel):
    engine_uid: str
    name: str
    status: bool = False
    management: int = 0
    day_start: time = time(8, 00)
    night_start: time = time(20, 00)
    engine_uid: str


class EcosystemUpdatePayload(BaseModel):
    name: str | None = None
    status: bool | None = None
    management: int | None = None
    day_start: time | None = None
    night_start: time | None = None
    engine_uid: str | None = None


EcosystemInfo = sqlalchemy_to_pydantic(
    Ecosystem,
    base=BaseModel,
    extra_fields={
        "connected": (bool, ...),
        "lighting_method": (Optional[gv.LightMethod], ...),
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


class EcosystemManagementInfo(BaseModel):
    ecosystem_uid: str = Field(alias="uid")
    sensors: bool = False
    light: bool = False
    climate: bool = False
    watering: bool = False
    health: bool = False
    alarms: bool = False
    pictures: bool = False
    database: bool = False
    switches: bool = False
    environment_data: bool = False
    plants_data: bool = False


# ---------------------------------------------------------------------------
#   Ecosystem lighting
# ---------------------------------------------------------------------------
class EcosystemLightingUpdatePayload(BaseModel):
    method: gv.LightMethod

    @field_validator("method", mode="before")
    def parse_method(cls, value):
        return safe_enum_from_name(gv.LightMethod, value)


class EcosystemLightInfo(BaseModel):
    ecosystem_uid: str
    method: gv.LightMethod = gv.LightMethod.fixed
    morning_start: time | None = None
    morning_end: time | None = None
    evening_start: time | None = None
    evening_end: time | None = None


# ---------------------------------------------------------------------------
#   Ecosystem climate parameter
# ---------------------------------------------------------------------------
class EnvironmentParameterCreationPayload(BaseModel):
    parameter: gv.ClimateParameter
    day: float
    night: float
    hysteresis: float = 0.0

    @field_validator("parameter", mode="before")
    def parse_parameter(cls, value):
        return safe_enum_from_name(gv.ClimateParameter, value)


class EnvironmentParameterUpdatePayload(BaseModel):
    day: float | None = None
    night: float | None = None
    hysteresis: float | None = None


EnvironmentParameterInfo = sqlalchemy_to_pydantic(
    EnvironmentParameter,
    base=BaseModel,
    exclude=["id"],
)


# ---------------------------------------------------------------------------
#   Ecosystem actuators
# ---------------------------------------------------------------------------
class EcosystemActuatorStatus(BaseModel):
    ecosystem_uid: str
    light: gv.ActuatorState = gv.ActuatorState()
    cooler: gv.ActuatorState = gv.ActuatorState()
    heater: gv.ActuatorState = gv.ActuatorState()
    humidifier: gv.ActuatorState = gv.ActuatorState()
    dehumidifier: gv.ActuatorState = gv.ActuatorState()
