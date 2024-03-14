from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_serializer

import gaia_validators as gv

from ouranos.core.database.models.gaia import SensorRecord
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic
from ouranos.web_server.validate.gaia.hardware import MeasureInfo, PlantInfo


EcosystemSensorDataUnit = sqlalchemy_to_pydantic(
    SensorRecord,
    base=BaseModel,
    exclude=["id"]
)


class EcosystemSensorData(BaseModel):
    ecosystem_uid: str
    data: list[EcosystemSensorDataUnit]


class SkSensorBaseInfo(BaseModel):
    uid: str
    name: str
    unit: str | None = None


class SkMeasureBaseInfo(BaseModel):
    measure: str
    units: list[str]
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
    current: list[SensorCurrentTimedValue] | None = None
    historic: list[SensorHistoricTimedValue] | None = None


class SensorOverview(BaseModel):
    uid: str
    ecosystem_uid: str
    name: str
    level: gv.HardwareLevel
    address: str
    type: gv.HardwareType
    model: str
    last_log: datetime | None
    measures: list[MeasureInfo]
    plants: list[PlantInfo]
    data: SensorOverviewData | None

    @field_serializer("type")
    def serialize_group(self, type: gv.HardwareType, _info):
        return type.name
