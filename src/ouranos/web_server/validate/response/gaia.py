from datetime import datetime

from typing import Optional
from pydantic import Field

from gaia_validators import HardwareLevel, HardwareType

from ouranos.core.database.models.common import WarningLevel
from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, Hardware, Light, Measure, Plant,
    SensorRecord)
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


EcosystemInfo = sqlalchemy_to_pydantic(
    Ecosystem,
    base=BaseModel,
    extra_fields={
        "connected": (bool, ...),
    }
)


EcosystemLightInfo = sqlalchemy_to_pydantic(
    Light,
    base=BaseModel,
    exclude=["id"]
)


class ManagementInfo(BaseModel):
    name: str
    value: int


class EcosystemManagementInfo(BaseModel):
    ecosystem_uid: str = Field(alias="uid")
    name: str
    sensors: bool = False
    light: bool = False
    climate: bool = False
    watering: bool = False
    health: bool = False
    alarms: bool = False
    webcam: bool = False
    switches: bool = False
    environment_data: bool = False
    plants_data: bool = False


EngineInfo = sqlalchemy_to_pydantic(
    Engine,
    base=BaseModel,
    extra_fields={
        "connected": (bool, ...),
        "ecosystems": (list[EcosystemInfo], ...)
    }
)


EnvironmentParameterInfo = sqlalchemy_to_pydantic(
    EnvironmentParameter,
    base=BaseModel,
    exclude=["id"]
)


MeasureInfo = sqlalchemy_to_pydantic(
    Measure,
    base=BaseModel,
    exclude=["id"]
)


PlantInfo = sqlalchemy_to_pydantic(
    Plant,
    base=BaseModel
)


HardwareInfo = sqlalchemy_to_pydantic(
    Hardware,
    base=BaseModel,
    extra_fields={
        "measures": (list[MeasureInfo], ...),
        "plants": (list[PlantInfo], ...)
    }
)


EcosystemSensorDataUnit = sqlalchemy_to_pydantic(
    SensorRecord,
    base=BaseModel,
    exclude=["id"]
)


class EcosystemSensorData(BaseModel):
    ecosystem_uid: str
    data: list[EcosystemSensorDataUnit]


class HardwareModelInfo(BaseModel):
    model: str
    type: HardwareType


class SkSensorBaseInfo(BaseModel):
    uid: str
    name: str


class SkMeasureBaseInfo(BaseModel):
    measure: str
    sensors: list[SkSensorBaseInfo]


class SensorSkeletonInfo(BaseModel):
    ecosystem_uid: str = Field(alias="uid")
    name: str
    level: list[HardwareLevel]
    sensors_skeleton: list[SkMeasureBaseInfo]


class GaiaWarningResult(BaseModel):
    level: WarningLevel
    title: str
    description: str


class SensorCurrentTimedValue(BaseModel):
    measure: str
    unit: str
    values: list[tuple[datetime, float]]


class SensorHistoricTimedValue(BaseModel):
    measure: str
    unit: str
    span: tuple[datetime, datetime]
    value: list[tuple[datetime, float]]


class SensorOverview(BaseModel):
    uid: str
    ecosystem_uid: str
    name: str
    level: HardwareLevel
    address: str
    type: HardwareType
    model: str
    status: bool
    last_log: Optional[datetime] = None
    measures: list[str]
    data: dict = Field(default_factory=dict)
