from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel, create_model
from sqlalchemy import Column, inspect
from sqlalchemy.orm import Mapper
from sqlalchemy.sql.functions import GenericFunction


def sqlalchemy_to_pydantic(
        db_model,
        exclude: list | None = None,
        base: Type[BaseModel] | None = None,
        prior_fields: dict[str, tuple[Type, Any]] | None = None,
        extra_fields: dict[str, tuple[Type, Any]] | None = None
) -> Type[BaseModel]:
    exclude: list = exclude or []
    fields: dict[str, tuple[Type, Any]] = {}
    if prior_fields:
        fields.update(prior_fields)
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
    if extra_fields:
        fields.update(extra_fields)
    return create_model(db_model.__name__, __base__=base, **fields)
