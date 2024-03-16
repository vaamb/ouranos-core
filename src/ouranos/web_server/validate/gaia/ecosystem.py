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


class EcosystemManagementConfig(gv.ManagementConfig):
    ecosystem_uid: str = Field(alias="uid")
    switches: bool = False
    environment_data: bool = False
    plants_data: bool = False


# ---------------------------------------------------------------------------
#   Ecosystem lighting
# ---------------------------------------------------------------------------
class EcosystemLightMethodUpdatePayload(BaseModel):
    method: gv.LightMethod

    @field_validator("method", mode="before")
    def parse_method(cls, value):
        return safe_enum_from_name(gv.LightMethod, value)


class EcosystemLightData(gv.LightData):
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
class EcosystemActuatorData(gv.ActuatorsData):
    ecosystem_uid: str
