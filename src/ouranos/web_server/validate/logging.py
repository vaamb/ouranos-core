from ouranos.core.database.models.logging import BaseLog
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


LogRecordInfo = sqlalchemy_to_pydantic(
    BaseLog,
    base=BaseModel,
    exclude=["id"]
)
