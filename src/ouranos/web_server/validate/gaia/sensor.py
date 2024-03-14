from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

import gaia_validators as gv

from ouranos.core.database.models.gaia import SensorRecord
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic
from ouranos.web_server.validate.gaia.hardware import HardwareInfo


# ---------------------------------------------------------------------------
#   Sensors skeleton
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
#   Current sensor data
# ---------------------------------------------------------------------------
_SensorRecordModel = sqlalchemy_to_pydantic(
    SensorRecord,
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
    data: SensorOverviewData | None

    model_config = ConfigDict(
        extra="allow",
    )
