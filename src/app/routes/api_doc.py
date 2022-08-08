from marshmallow import (
    ValidationError, Schema, fields as ma_fields, validates, INCLUDE
)

from src.consts import (
    HARDWARE_LEVELS as _HARDWARE_LEVELS, HARDWARE_TYPE as _HARDWARE_TYPE
)


HARDWARE_TYPE = _HARDWARE_TYPE + ["all"]
HARDWARE_LEVELS = _HARDWARE_LEVELS + ["all"]


def no_default(param: dict):
    rv = param
    keys = list(rv.keys())
    for key in keys:
        rv[key].pop("default", None)
    return rv


class BaseSchema(Schema):
    class Meta:
        unknown = INCLUDE


class EnginesQuerySchema(BaseSchema):
    uid = ma_fields.Field(missing="all")


engines_query_schema = EnginesQuerySchema()


class EcosystemsQuerySchema(BaseSchema):
    uid = ma_fields.Field(missing="recent")


ecosystem_query_schema = EcosystemsQuerySchema()


class HardwareQuerySchema(BaseSchema):
    uid = ma_fields.Field(missing="all")
    level = ma_fields.Field(missing="all")
    type = ma_fields.Field(missing="all")
    model = ma_fields.Field(missing="all")
    measures = ma_fields.Field(missing="all")
    current_data = ma_fields.Boolean(missing=True)
    historic_data = ma_fields.Boolean(missing=True)

    @validates("level")
    def validate_level(self, value):
        if isinstance(value, str):
            value = value.split(",")
        if not all([item in HARDWARE_LEVELS for item in value]):
            raise ValidationError(f"Must be in {HARDWARE_LEVELS}")

    @validates("type")
    def validate_hardware(self, value):
        if isinstance(value, str):
            value = value.split(",")
        if not all([item in HARDWARE_TYPE for item in value]):
            raise ValidationError(f"Must be in {HARDWARE_TYPE}")


hardware_query_schema = HardwareQuerySchema()


authorizations = {
    "basic_auth": {
        "type": "basic",
    },
    "cookie_auth": {
        "name": "session",
        "type": "apiKey",
        "in": "cookie",
    }
}


manager_param = {
    "uid": {
        "description": "Ecosystem UID or 'all', 'recent' or 'connected'",
        "type": "str",
        "default": "recent",
    },
}

ecosystem_param = {
    "uid": {
        "description": "Ecosystem UID or 'all', 'recent' or 'connected'",
        "type": "str",
        "default": "recent",
    },
}

hardware_param = {
    "uid": {
        "description": "Hardware uid",
        "type": "str",
        "default": "all"
    },
}

level_param = {
    "level": {
        "description": "Hardware level",
        "type": "str",
        "default": "all"
    },
}

type_param = {
    "type": {
        "description": "Hardware type",
        "type": "str",
        "default": "all"
    },
}

model_param = {
    "model": {
        "description": "Hardware model",
        "type": "str",
        "default": "all"
    },
}

measure_param = {
    "measure": {
        "description": "name of the measure",
        "type": "str",
        "default": "all",
    },
}


time_window_params = {
    "start_time": {
        "description": "Lower datetime limit of the query, written in ISO 8601 "
                       "format",
        "type": "str",
    },
    "end_time": {
        "description": "Higher datetime limit of the query, written in ISO 8601 "
                       "format",
        "type": "str",
    },
}


data_params = {
    "current_data": {
        "description": "fetch current data",
        "type": "bool",
        "default": True,
    },
    "historic_data": {
        "description": "fetch historic data",
        "type": "bool",
        "default": True,
    },
    **time_window_params,
}
