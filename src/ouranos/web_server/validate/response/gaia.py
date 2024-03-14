from datetime import datetime

from typing import Optional
from pydantic import Field, field_serializer

import gaia_validators as gv

from ouranos.core.database.models.gaia import (
    CrudRequest, Engine, Plant, SensorRecord)
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


class EcosystemSummary(BaseModel):
    uid: str
    name: str


EngineInfo = sqlalchemy_to_pydantic(
    Engine,
    base=BaseModel,
    extra_fields={
        "connected": (bool, ...),
        "ecosystems": (list[EcosystemSummary], ...)
    }
)


class MeasureInfo(BaseModel):
    name: str
    unit: Optional[str]


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
    unit: Optional[str]


class SkMeasureBaseInfo(BaseModel):
    measure: str
    units: list[Optional[str]]
    sensors: list[SkSensorBaseInfo]


class SensorSkeletonInfo(BaseModel):
    ecosystem_uid: str = Field(alias="uid")
    name: str
    level: list[gv.HardwareLevel]
    sensors_skeleton: list[SkMeasureBaseInfo]


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
