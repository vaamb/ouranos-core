from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel, create_model
from sqlalchemy import Column, inspect
from sqlalchemy.orm import Mapper
from sqlalchemy.sql.functions import GenericFunction


def sqlalchemy_to_pydantic(
        db_model,
        exclude: list | None = None,
        base: Type[BaseModel] | None = None
):
    exclude: list = exclude or []
    fields: dict[str, tuple[Type, Any | None]] = {}
    mapper: Mapper = inspect(db_model)
    for column in mapper.columns._all_columns:
        column: Column
        name = column.key
        if name in exclude:
            continue
        try:
            python_type = column.type.python_type
        except Exception:
            # Column type is a custom type implementing a base sqlalchemy type
            python_type = column.type.impl.python_type
        default = None
        if column.default is None and not column.nullable:
            default = ...
        elif column.default is not None:
            if isinstance(column.default.arg, GenericFunction):
                default = ...
            else:
                default = column.default.arg
        fields[name] = (python_type, default)
    return create_model(db_model.__name__, __base__=base, **fields)


class ExtendedModel(BaseModel):
    @classmethod
    def get_properties(cls):
        return [
            prop for prop in dir(cls)
            if isinstance(getattr(cls, prop), property)
        ]

    def dict(self, *args, **kwargs):
        self.__dict__.update(
            {prop: getattr(self, prop) for prop in self.get_properties()}
        )
        return super().dict(*args, **kwargs)

    class Config:
        orm_mode = True
