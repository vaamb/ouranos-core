from datetime import datetime, time

from typing import Optional
from pydantic import Field, field_serializer

import gaia_validators as gv

from ouranos.core.database.models.common import WarningLevel
from ouranos.core.database.models.gaia import (
    CrudRequest, Ecosystem, Engine, EnvironmentParameter, Hardware, Measure,
    Plant, SensorRecord)
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


EcosystemInfo = sqlalchemy_to_pydantic(
    Ecosystem,
    base=BaseModel,
    extra_fields={
        "connected": (bool, ...),
        "lighting_method": (Optional[gv.LightMethod], ...)
    }
)


class EcosystemLightInfo(BaseModel):
    ecosystem_uid: str
    method: gv.LightMethod = gv.LightMethod.fixed
    morning_start: Optional[time] = None
    morning_end: Optional[time] = None
    evening_start: Optional[time] = None
    evening_end: Optional[time] = None


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


class HardwareInfo(BaseModel):
    uid: str
    ecosystem_uid: str
    name: str
    level: gv.HardwareLevel
    address: str
    type: gv.HardwareType
    model: str
    last_log: Optional[datetime] = None
    measures: list[MeasureInfo]
    plants: list[PlantInfo]

    @field_serializer("type")
    def serialize_group(self, type: gv.HardwareType, _info):
        return type.name


EcosystemSensorDataUnit = sqlalchemy_to_pydantic(
    SensorRecord,
    base=BaseModel,
    exclude=["id"]
)


class EcosystemSensorData(BaseModel):
    ecosystem_uid: str
    data: list[EcosystemSensorDataUnit]


class EcosystemActuatorStatus(BaseModel):
    ecosystem_uid: str
    light: gv.ActuatorState = gv.ActuatorState()
    cooler: gv.ActuatorState = gv.ActuatorState()
    heater: gv.ActuatorState = gv.ActuatorState()
    humidifier: gv.ActuatorState = gv.ActuatorState()
    dehumidifier: gv.ActuatorState = gv.ActuatorState()


class HardwareModelInfo(BaseModel):
    model: str
    type: gv.HardwareType

    @field_serializer("type")
    def serialize_group(self, type: gv.HardwareType, _info):
        return type.name


class SkSensorBaseInfo(BaseModel):
    uid: str
    name: str


class SkMeasureBaseInfo(BaseModel):
    measure: str
    sensors: list[SkSensorBaseInfo]


class SensorSkeletonInfo(BaseModel):
    ecosystem_uid: str = Field(alias="uid")
    name: str
    level: list[gv.HardwareLevel]
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
    values: list[tuple[datetime, float]]


class SensorOverviewData(BaseModel):
    current: Optional[list[SensorCurrentTimedValue]] = None
    historic: Optional[list[SensorHistoricTimedValue]] = None


class SensorOverview(BaseModel):
    uid: str
    ecosystem_uid: str
    name: str
    level: gv.HardwareLevel
    address: str
    type: gv.HardwareType
    model: str
    last_log: Optional[datetime]
    measures: list[MeasureInfo]
    plants: list[PlantInfo]
    data: Optional[SensorOverviewData]

    @field_serializer("type")
    def serialize_group(self, type: gv.HardwareType, _info):
        return type.name


CrudRequestInfo = sqlalchemy_to_pydantic(
    CrudRequest,
    base=BaseModel,
    extra_fields={
        "completed": (bool, ...),
    }
)
