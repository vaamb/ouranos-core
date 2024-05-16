from __future__ import annotations

from datetime import datetime

from pydantic import Field

import gaia_validators as gv

from ouranos.core.database.models.gaia import SensorDataRecord
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic
from ouranos.web_server.validate.gaia.hardware import HardwareInfo


# ---------------------------------------------------------------------------
#   Sensors skeleton
# ---------------------------------------------------------------------------
class _SkSensorBaseInfo(BaseModel):
    uid: str
    name: str
    unit: str | None = None


class _SkMeasureBaseInfo(BaseModel):
    measure: str
    units: list[str] = Field(default_factory=list)
    sensors: list[_SkSensorBaseInfo]


class SensorSkeletonInfo(BaseModel):
    ecosystem_uid: str = Field(alias="uid")
    name: str
    level: list[gv.HardwareLevel]
    sensors_skeleton: list[_SkMeasureBaseInfo]


# ---------------------------------------------------------------------------
#   Current sensor data
# ---------------------------------------------------------------------------
_SensorRecordModel = sqlalchemy_to_pydantic(
    SensorDataRecord,
    base=BaseModel,
    exclude=["id"]
)


class EcosystemSensorData(BaseModel):
    ecosystem_uid: str
    data: list[_SensorRecordModel]


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


class SensorOverview(HardwareInfo):
    data: SensorOverviewData | None = None
