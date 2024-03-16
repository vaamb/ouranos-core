from ouranos.core.database.models.gaia import CrudRequest, Engine
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


class _EcosystemSummary(BaseModel):
    uid: str
    name: str


EngineInfo = sqlalchemy_to_pydantic(
    Engine,
    base=BaseModel,
    extra_fields={
        "connected": (bool, ...),
        "ecosystems": (list[_EcosystemSummary], ...)
    }
)


CrudRequestInfo = sqlalchemy_to_pydantic(
    CrudRequest,
    base=BaseModel,
    extra_fields={
        "completed": (bool, ...),
    }
)
