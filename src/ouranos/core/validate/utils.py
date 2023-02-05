from __future__ import annotations

from typing import Any, Type

from pydantic import create_model
from sqlalchemy import Column, inspect
from sqlalchemy.orm import Mapper


def sqlalchemy_to_pydantic(
        db_model, exclude: list | None = None
):
    exclude: list = exclude or []
    fields: dict[str, tuple[Type, Any | None]] = {}
    mapper: Mapper = inspect(db_model)
    for column in mapper.columns._all_columns:
        column: Column
        name = column.key
        if name in exclude:
            continue
        python_type = column.type.python_type
        default = None
        if column.default is None and not column.nullable:
            default = ...
        elif column.default is not None:
            default = column.default.arg
        fields[name] = (python_type, default)
    return create_model(db_model.__name__, **fields)
