from datetime import datetime, time, timedelta

from pydantic import BaseModel

from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, Hardware, HardwareLevel,
    HardwareType, Light, Measure
)
from ouranos.core.validate.utils import ExtendedModel, sqlalchemy_to_pydantic


class ecosystem_creation(BaseModel):
    name: str
    status: bool = False
    management: int = 0
    day_start: time = time(8, 00)
    night_start: time = time(20, 00)
    engine_uid: int


_ecosystem = sqlalchemy_to_pydantic(Ecosystem, base=ExtendedModel)


class ecosystem(_ecosystem):
    @property
    def connected(self) -> bool:
        return datetime.utcnow() - self.last_seen <= timedelta(seconds=30.0)


ecosystem_light = sqlalchemy_to_pydantic(Light, exclude=["id"], base=ExtendedModel)


class ecosystem_management(ExtendedModel):
    uid: str
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


_engine = sqlalchemy_to_pydantic(Engine, base=ExtendedModel)


class engine(_engine):
    ecosystems: list[ecosystem]

    @property
    def connected(self) -> bool:
        return self.last_seen - datetime.now() >= timedelta(seconds=30.0)


class hardware_creation(ExtendedModel):
    ecosystem_uid: str
    name: str
    level: HardwareLevel
    address: str
    type: HardwareType
    model: str
    status: bool = True
    plant_uid: list[str]


hardware = sqlalchemy_to_pydantic(Hardware, base=ExtendedModel)


environment_parameter = sqlalchemy_to_pydantic(EnvironmentParameter, base=ExtendedModel)


measure = sqlalchemy_to_pydantic(Measure, exclude=["id"], base=ExtendedModel)
