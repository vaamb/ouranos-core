from flask import request, jsonify
from flask_restx import Namespace, Resource, fields
from marshmallow import ValidationError, Schema, fields as ma_fields, \
    validate, validates

from src.app import API, db

ALL_HARDWARE = (*API.ecosystems.ALL_HARDWARE, "all")
SENSOR_LEVELS = ("plants", "ecosystems", "all")
DEFAULT_ECOSYSTEMS = "recent"


class StringToTuple(ma_fields.Field):
    def _deserialize(self, value, attr, data, **kwargs) -> tuple:
        rv = None
        if isinstance(value, (list, tuple)):
            rv = *value,
        if isinstance(value, str):
            rv = *value.split(","),
        else:
            raise ValidationError("Field should be str, list or tuple")
        if "all" in rv:
            return "all",
        return rv


class EcosystemsQuerySchema(Schema):
    ecosystems = StringToTuple(missing="recent")
    scope = ma_fields.String(missing="current",
                             validate=validate.OneOf(("current", "historic")))
    start_time = ma_fields.DateTime(format="iso")
    end_time = ma_fields.DateTime(format="iso")
    level = StringToTuple(missing=("all",))
    hardware_type = StringToTuple(missing=("all",))

    @validates("level")
    def validate_level(self, value):
        if isinstance(value, str):
            value = (value, )
        if not all([item in SENSOR_LEVELS for item in value]):
            raise ValidationError(f"Elements must be of {SENSOR_LEVELS}")

    @validates("hardware_type")
    def validate_hardware(self, value):
        if isinstance(value, str):
            value = (value, )
        if not all([item in ALL_HARDWARE for item in value]):
            raise ValidationError(f"Elements must be of {ALL_HARDWARE}")


namespace = Namespace(
    "ecosystems",
    description="Information about the registered ecosystems.",
    path="/eco",
)


ecosystems_param = {
    "ecosystems": {"description": "ecosystems UID or name", "type": "str",
                   "default": "recent"},
}

time_window_params = {
    "start_time": {"description": "lower datetime limit of the query, written "
                                  "in ISO 8601 format.",
                   "type": "str"},
    "end_time": {"description": "higher datetime limit of the query, written "
                                "in ISO 8601 format",
                 "type": "str"},
}


@namespace.route("/management_summary")
class ManagementSummary(Resource):
    def get(self):
        """Doc string here"""
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems="recent")
        ecosystems_info = API.ecosystems.get_ecosystems_management(
            session=db.session, ecosystems_query_obj=ecosystem_qo)
        functionalities = API.ecosystems.summarize_ecosystems_management(
            session=db.session, ecosystems_info=ecosystems_info)
        return jsonify(functionalities)


@namespace.route("/status")
class Status(Resource):
    @namespace.doc(params={**ecosystems_param})
    def get(self):
        ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(
            ",")
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems=ecosystems)
        response = API.ecosystems.get_ecosystems(
            session=db.session, ecosystems_query_obj=ecosystem_qo)
        return jsonify(response)


@namespace.route("/management")
class Management(Resource):
    @namespace.doc(params={**ecosystems_param})
    def get(self):
        ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems=ecosystems)
        response = API.ecosystems.get_ecosystems_management(
            session=db.session, ecosystems_query_obj=ecosystem_qo)
        return jsonify(response)


@namespace.route("/sensors_skeleton")
class SensorsSkeleton(Resource):
    @namespace.doc(params={
        **ecosystems_param, **time_window_params,
        "level": {
            "description": "sensor level, either 'ecosystem', 'plants' or "
                           "'all' [default]",
            "choices": [1, 2],
            "default": "all",
            "type": "str",
        },
    })
    def get(self):
        ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
        level = request.args.get("level", "all")
        # TODO: think about time later
        start_time = request.args.get("start_time", None)
        end_time = request.args.get("end_time", None)
        time_window = API.utils.create_time_window(start_time, end_time)
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems=ecosystems
        )
        response = API.ecosystems.get_ecosystems_sensors_data_skeleton(
            session=db.session, ecosystems_query_obj=ecosystem_qo,
            time_window=time_window, level=level
        )
        return jsonify(response)


@namespace.route("/sensors")
class Sensors(Resource):
    @namespace.doc(params={
        **ecosystems_param,
        "scope": {
            "description": "time scope, either 'current' [default] or "
                           "'historic'",
            "type": "str",
        },
    })
    def get(self):
        ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
        scope = request.args.get("scope", "current")
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems=ecosystems)
        if scope == "current":
            response = API.ecosystems.get_current_sensors_data(
                session=db.session, ecosystems_query_obj=ecosystem_qo
            )
        elif scope == "historic":
            response = "To be done"
        else:
            response = "Choose scope from 'current' or 'historic'"
        return jsonify(response)


@namespace.route("/sensors/<uid>")
class SensorByUID(Resource):
    @namespace.doc(params={
        **time_window_params,
        "uid": {
            "description": "sensor uid",
            "type": "str",
        },
    })
    def get(self, uid: str):
        start_time = request.args.get("start_time", None)
        end_time = request.args.get("end_time", None)
        time_window = API.utils.create_time_window(start_time, end_time)
        response = API.ecosystems.get_historic_sensors_data_by_sensor(
            session=db.session, sensor_uid=uid, measures="all",
            time_window=time_window,
        )
        return jsonify(response)


@namespace.route("/sensors/<uid>/<measure>")
class Sensor(Resource):
    @namespace.doc(params={
        **ecosystems_param, **time_window_params,
        "uid": {
            "description": "sensor uid",
            "type": "str",
        },
        "measure": {
            "description": "name of the measure",
            "type": "str",
        }
    })
    @namespace.marshal_with(sensor_data)
    def get(self, uid: str, measure: str = None):
        start_time = request.args.get("start_time", None)
        end_time = request.args.get("end_time", None)
        time_window = API.utils.create_time_window(start_time, end_time)
        response = API.ecosystems.get_historic_sensor_data(
            session=db.session, sensor_uid=uid, measure=measure,
            time_window=time_window,
        )

        return {
            "measure": measure, "sensor_uid": uid, "values": response
        }


@namespace.route("/hardware")
class Hardware(Resource):
    @namespace.doc(params={
        **ecosystems_param, **time_window_params,
        "level": {
            "description": "sensor level, either 'ecosystem', 'plants' or "
                           "'all' [default]",
            "type": "str",
        },
    })
    def get(self):
        ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
        level = request.args.get("level", "all").split(",")
        hardware_type = request.args.get("hardware_type", "all").split(",")
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems=ecosystems
        )
        response = API.ecosystems.get_hardware(
            session=db.session, ecosystems_query_obj=ecosystem_qo, level=level,
            hardware_type=hardware_type
        )
        return jsonify(response)

    def post(self):
        pass  # TODO: get info and create hardware


@namespace.route("/hardware/<uid>")
class HardwareByUID(Resource):
    @namespace.doc(params={
        "uid": {
            "description": "hardware uid",
            "type": "str",
        },
    })
    def get(self, uid: str):
        response = API.ecosystems.get_hardware_by_uid(
            session=db.session, hardware_uid=uid)
        return jsonify(response)


@namespace.route("/light")
class Light(Resource):
    @namespace.doc(params={**ecosystems_param})
    def get(self):
        ecosystems = request.args.get("ecosystems", DEFAULT_ECOSYSTEMS).split(",")
        ecosystem_qo = API.ecosystems.get_ecosystems_query_obj(
            session=db.session, ecosystems=ecosystems
        )
        response = API.ecosystems.get_light_info(ecosystem_qo)
        return jsonify(response)
