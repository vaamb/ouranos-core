from __future__ import annotations

from datetime import time
from typing import Optional

from pydantic import ConfigDict, Field, field_validator

import gaia_validators as gv
from gaia_validators import safe_enum_from_name

from ouranos.core.database.models.gaia import Ecosystem
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


# ---------------------------------------------------------------------------
#   Base ecosystem
# ---------------------------------------------------------------------------
class EcosystemCreationPayload(BaseModel):
    name: str
    status: bool = False
    management: int = 0
    lighting_method: gv.LightingMethod = gv.LightingMethod.fixed
    day_start: time = time(8, 00)
    night_start: time = time(20, 00)
    engine_uid: str


class EcosystemUpdatePayload(BaseModel):
    name: str | None = None
    status: bool | None = None
    management: int | None = None
    lighting_method: gv.LightingMethod | None = None
    day_start: time | None = None
    night_start: time | None = None
    engine_uid: str | None = None


EcosystemInfo = sqlalchemy_to_pydantic(
    Ecosystem,
    base=BaseModel,
    extra_fields={
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


class EcosystemManagementInfo(gv.ManagementConfig):
    ecosystem_uid: str = Field(alias="uid")
    switches: bool = False
    environment_data: bool = False
    plants_data: bool = False


# ---------------------------------------------------------------------------
#   Ecosystem lighting
# ---------------------------------------------------------------------------
class EcosystemLightMethodUpdatePayload(BaseModel):
    method: gv.LightingMethod

    @field_validator("method", mode="before")
    def parse_method(cls, value):
        return safe_enum_from_name(gv.LightingMethod, value)


class EcosystemLightInfo(gv.LightData):
    ecosystem_uid: str


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


EnvironmentParameterInfo = EnvironmentParameterCreationPayload


# ---------------------------------------------------------------------------
#   Ecosystem actuators
# ---------------------------------------------------------------------------
class EcosystemActuatorInfo(gv.ActuatorsData):
    ecosystem_uid: str
