from flask import abort, request, jsonify
from flask_restx import Resource

from . import namespace
from ..api_doc import (
    hardware_query_schema, hardware_param, level_param, type_param, model_param,
    measure_param, data_params, no_default
)
from ..decorators import permission_required
from ..utils import get_time_window_from_request_args
from src import api
from src.app import db
from src.database.models.app import Permission


ecosystem_param = {
    "e_uid": {
        "description": "Ecosystem UID",
        "type": "str",
        "default": "all",
    },
}


@namespace.route("/hardware")
class Hardware(Resource):
    @namespace.doc(
        description="Get the info of the list of hardware listed in the query string",
        params={
            **ecosystem_param, **hardware_param, **level_param, **type_param,
            **model_param
        }
    )
    def get(self):
        qs = hardware_query_schema.load(request.args)
        qs["e_uid"] = request.args.get("ecosystem_uid", "all")
        time_window = get_time_window_from_request_args()
        hardware = api.gaia.get_hardware(
            db.session, qs["uid"], qs["e_uid"], qs["level"], qs["type"],
            qs["model"]
        )
        response = [api.gaia.get_sensor_info(
            db.session, h, qs["measures"], qs["current_data"],
            qs["historic_data"], time_window
        ) for h in hardware]
        return jsonify(response)


@namespace.route("/hardware/models_available")
@namespace.doc(description="Get the info of the list of hardware listed in the query string")
class HardwareAvailable(Resource):
    def get(self):
        response = api.gaia.get_hardware_models_available()
        return jsonify(response)


@namespace.route("/hardware/u")
class HardwareUPost(Resource):
    @namespace.doc(params={**no_default(hardware_param)})
    @permission_required(Permission.OPERATE)
    def post(self):
        try:
            hardware_dict = request.json["data"]

            print(hardware_dict)
            uid = "truc"
            return {"msg": f"New hardware with uid '{uid}' created"}
        except KeyError:
            return {"msg": "The server could not parse the data"}, 500


@namespace.route("/hardware/u/<uid>")
class HardwareU(Resource):
    @namespace.doc(params={**no_default(hardware_param)})
    def get(self, uid: str):
        hardware = api.gaia.get_hardware(
            db.session, uid, "all", "all", "all", "all"
        )
        if hardware:
            response = api.gaia.get_hardware_info(db.session, hardware[0])
            return jsonify(response)
        return {"error": f"Hardware not found"}, 404

    @namespace.doc(params={**no_default(hardware_param)})
    @permission_required(Permission.OPERATE)
    def put(self, uid: str):
        hardware_dict = request.json["data"]
        try:
            api.gaia.update_hardware(
                session=db.session, hardware_uid=uid,
                hardware_dict=hardware_dict
            )
            db.session.commit()
            return {"msg": f"Hardware with uid '{uid}' has been updated"}
        except api.exceptions.WrongDataFormat as e:
            return {"msg": str(e)}, 400

    @namespace.doc(params={**no_default(hardware_param)})
    @permission_required(Permission.OPERATE)
    def delete(self, uid: str):
        api.gaia.delete_hardware(session=db.session, hardware_uid=uid)
        return {"msg": f"Hardware with uid '{uid}' has been deleted"}


@namespace.route("/sensor")
class Sensor(Resource):
    @namespace.doc(params={
        **ecosystem_param, **hardware_param, **level_param, **type_param,
        **model_param, **measure_param, **data_params,
    })
    def get(self):
        qs = hardware_query_schema.load(request.args)
        qs["e_uid"] = request.args.get("ecosystem_uid", "all")
        time_window = get_time_window_from_request_args()
        sensors = api.gaia.get_hardware(
            db.session, qs["uid"], qs["e_uid"], qs["level"], "sensor",
            qs["model"]
        )
        response = [api.gaia.get_sensor_info(
            db.session, sensor, qs["measures"], qs["current_data"],
            qs["historic_data"], time_window
        ) for sensor in sensors]
        return jsonify(response)


@namespace.route("/sensor/measures")
class SensorMeasures(Resource):
    @namespace.doc(description="Get a list of measures logged")
    def get(self):
        return api.gaia.get_measures(db.session)


@namespace.route("/sensor/u/<uid>")
class SensorU(Resource):
    @namespace.doc(params={**no_default(hardware_param), **data_params})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/sensors to get more than one sensor"})
        qs = hardware_query_schema.load(request.args)
        time_window = get_time_window_from_request_args()
        sensor = api.gaia.get_hardware(
            db.session, uid, "all", "all", "sensor", "all"
        )
        if sensor:
            response = api.gaia.get_sensor_info(
                db.session, sensor[0], "all", qs["current_data"],
                qs["historic_data"], time_window,
            )
            return jsonify(response)
        return {"error": "Sensor not found"}, 404


@namespace.route("/sensor/u/<uid>/<measure>")
class SensorUForMeasure(Resource):
    @namespace.doc(params={
        **no_default(hardware_param), **no_default(measure_param), **data_params
    })
    def get(self, uid: str, measure: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "use api/gaia/sensors to get more than one sensor"})
        if "all" in measure or len(measure.split(",")) > 1:
            abort(303, {"error": "use api/gaia/sensor/uid to get more than one measure"})
        qs = hardware_query_schema.load(request.args)
        time_window = get_time_window_from_request_args()
        sensor = api.gaia.get_hardware(
            db.session, uid, "all", "all", "sensor", "all"
        )
        if sensor:
            if measure in [m.name for m in sensor[0].measure]:
                response = api.gaia.get_sensor_info(
                    db.session, sensor[0], measure, qs["current_data"],
                    qs["historic_data"], time_window
                )
                return jsonify(response)
            else:
                return {"error": f"Sensor {uid} does not measure {measure}"}, 404
        return {"error": "Sensor not found"}, 404
