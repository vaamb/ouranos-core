from datetime import time
from typing import Optional

from gaia_validators import HardwareLevel, HardwareType

from ouranos.core.validate.base import BaseModel


class EcosystemCreationPayload(BaseModel):
    name: str
    status: bool = False
    management: int = 0
    day_start: time = time(8, 00)
    night_start: time = time(20, 00)
    engine_uid: str


class EcosystemUpdatePayload(BaseModel):
    name: Optional[str] = None
    status: Optional[bool] = None
    management: Optional[int] = None
    day_start: Optional[time] = None
    night_start: Optional[time] = None
    engine_uid: Optional[str] = None


class HardwareCreationPayload(BaseModel):
    ecosystem_uid: str
    name: str
    level: HardwareLevel
    address: str
    type: HardwareType
    model: str
    status: bool = True
    measure: Optional[list[str]] = None
    plant_uid: Optional[list[str]] = None


class HardwareUpdatePayload(BaseModel):
    ecosystem_uid: Optional[str] = None
    name: Optional[str] = None
    level: Optional[HardwareLevel] = None
    address: Optional[str] = None
    type: Optional[HardwareType] = None
    model: Optional[str] = None
    status: Optional[bool] = None
    measure: Optional[list[str]] = None
    plant_uid: Optional[list[str]] = None
