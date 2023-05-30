from ouranos.core.database.models import SystemRecord
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


SystemRecordResponse = sqlalchemy_to_pydantic(SystemRecord, exclude=["id"])
