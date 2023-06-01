from datetime import time

from gaia_validators import HardwareLevel, HardwareType

from ouranos.core.validate.base import BaseModel


class EcosystemPayload(BaseModel):
    name: str
    status: bool = False
    management: int = 0
    day_start: time = time(8, 00)
    night_start: time = time(20, 00)
    engine_uid: str


class HardwarePayload(BaseModel):
    ecosystem_uid: str
    name: str
    level: HardwareLevel
    address: str
    type: HardwareType
    model: str
    status: bool = True
    plant_uid: list[str]
