from __future__ import annotations

from typing import Any, Optional, Type

from pydantic import BaseModel, create_model
from sqlalchemy import Column, inspect
from sqlalchemy.orm import Mapper
from sqlalchemy.sql.functions import GenericFunction
from sqlalchemy.sql.schema import ColumnDefault
from sqlalchemy.types import TypeDecorator


def sqlalchemy_to_pydantic(
        db_model,
        exclude: list | None = None,
        base: Type[BaseModel] | None = None,
        prior_fields: dict[str, tuple[Any, Any]] | None = None,
        extra_fields: dict[str, tuple[Any, Any]] | None = None
) -> Any:
    # The dynamically created pydantic model cannot be given a precise static
    # type, hence the `Any` return type instead of `Type[BaseModel]`
    exclude: list = exclude or []
    fields: dict[str, tuple[Any, Any]] = {}
    if prior_fields:
        fields.update(prior_fields)
    mapper: Mapper = inspect(db_model)
    for column in mapper.columns._all_columns:
        column: Column
        name = column.key
        if name in exclude:
            continue
        # Get python type
        python_type: Any
        try:
            python_type = column.type.python_type
        except Exception:
            # Column type is a custom type implementing a base sqlalchemy type
            column_type = column.type
            assert isinstance(column_type, TypeDecorator)
            python_type = column_type.impl.python_type
        if column.nullable:
            python_type = Optional[python_type]  # ty: ignore[invalid-type-form]
        # Get default value
        default: Any = None
        if column.default is None and not column.nullable:
            default = ...
        elif isinstance(column.default, ColumnDefault):
            if isinstance(column.default.arg, GenericFunction):
                default = ...
            else:
                default = column.default.arg
        fields[name] = (python_type, default)
    if extra_fields:
        fields.update(extra_fields)
    if base is not None:
        return create_model(db_model.__name__, __base__=base, **fields)  # ty: ignore[no-matching-overload]
    return create_model(db_model.__name__, **fields)  # ty: ignore[no-matching-overload]
