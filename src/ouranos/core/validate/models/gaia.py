from datetime import time

from pydantic import BaseModel
from ouranos.core.database.models.gaia import HardwareLevel, HardwareType


class ecosystem_creation(BaseModel):
    name: str
    status: bool = False
    management: int = 0
    day_start: time = time(8, 00)
    night_start: time = time(20, 00)
    engine_uid: int


class ecosystem(BaseModel):
    pass


class hardware_creation(BaseModel):
    ecosystem_uid: str
    name: str
    level: HardwareLevel
    address: str
    type: HardwareType
    model: str
    status: bool = True
    plant_uid: list[str]


class hardware(BaseModel):
    pass
