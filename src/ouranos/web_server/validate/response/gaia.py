from ouranos.core.database.models.gaia import (
    Ecosystem, Engine, EnvironmentParameter, Hardware, Light, Measure, Plant)

from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


EcosystemInfo = sqlalchemy_to_pydantic(
    Ecosystem,
    base=BaseModel,
    extra_fields={
        "connected": (bool, ...),
    }
)


EcosystemLightInfo = sqlalchemy_to_pydantic(
    Light,
    base=BaseModel,
    exclude=["id"]
)


class EcosystemManagementInfo(BaseModel):
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


HardwareInfo = sqlalchemy_to_pydantic(
    Hardware,
    base=BaseModel,
    extra_fields={
        "measures": (list[MeasureInfo], ...),
        "plants": (list[PlantInfo], ...)
    }
)
