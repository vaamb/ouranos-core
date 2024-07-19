from __future__ import annotations

from datetime import datetime

from pydantic import Field

import gaia_validators as gv

from ouranos.core.database.models.gaia import SensorDataRecord
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


# ---------------------------------------------------------------------------
#   Sensors skeleton
# ---------------------------------------------------------------------------
class SkSensorBaseInfo(BaseModel):
    uid: str
    name: str
    unit: str | None = None


class SkMeasureBaseInfo(BaseModel):
    measure: str
    units: list[str] = Field(default_factory=list)
    sensors: list[SkSensorBaseInfo]


class SensorSkeletonInfo(BaseModel):
    uid: str
    name: str
    level: list[gv.HardwareLevel]
    span: tuple[datetime, datetime]
    sensors_skeleton: list[SkMeasureBaseInfo]


# ---------------------------------------------------------------------------
#   Current sensor data
# ---------------------------------------------------------------------------
SensorRecordModel = sqlalchemy_to_pydantic(
    SensorDataRecord,
    base=BaseModel,
    exclude=["id"]
)


class EcosystemSensorData(BaseModel):
    uid: str
    name: str
    values: list[SensorRecordModel]


class SensorMeasureCurrentTimedValue(BaseModel):
    uid: str
    measure: str
    unit: str
    order: tuple[str, str] = ("timestamp", "value")
    values: list[tuple[datetime, float]]


class SensorMeasureHistoricTimedValue(BaseModel):
    uid: str
    measure: str
    unit: str
    span: tuple[datetime, datetime]
    order: tuple[str, str] = ("timestamp", "value")
    values: list[tuple[datetime, float]]
