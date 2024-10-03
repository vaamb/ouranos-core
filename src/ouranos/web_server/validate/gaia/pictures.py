from __future__ import annotations

from ouranos.core.database.models.gaia import CameraPicture
from ouranos.core.validate.base import BaseModel
from ouranos.core.validate.utils import sqlalchemy_to_pydantic


CameraPictureInfo = sqlalchemy_to_pydantic(
    CameraPicture,
    base=BaseModel,
)
