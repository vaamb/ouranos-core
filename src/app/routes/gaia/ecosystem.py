from flask import abort, request, jsonify
from flask_restx import Resource

from . import namespace
from ..api_doc import (
    ecosystem_query_schema, ecosystem_param, time_window_params, level_param,
    no_default
)
from ..decorators import permission_required
from ..utils import get_time_window_from_request_args
from src import api
from src.app import db
from src.database.models.app import Permission


def ecosystems_or_abort(ecosystems):
    ecosystems_qo = api.gaia.get_ecosystems(
        session=db.session, ecosystems=ecosystems
    )
    if ecosystems_qo:
        return ecosystems_qo
    abort(404, {"error": f"Ecosystem(s) not found"})


@namespace.route("/ecosystem")
class Ecosystem(Resource):
    @namespace.doc(params={**ecosystem_param})
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        response = [api.gaia.get_ecosystem_info(
            db.session, ecosystem
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u")
class EcosystemUPost(Resource):
    @permission_required(Permission.OPERATE)
    def post(self):
        pass


@namespace.route("/ecosystem/u/<uid>")
class EcosystemS(Resource):
    @namespace.doc(params={**no_default(ecosystem_param)})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems to get more than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        if ecosystem:
            response = api.gaia.get_ecosystem_info(db.session, ecosystem[0])
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404

    @namespace.doc(params={**no_default(ecosystem_param)})
    @permission_required(Permission.OPERATE)
    def put(self, uid: str):
        pass

    @namespace.doc(params={**no_default(ecosystem_param)})
    @permission_required(Permission.OPERATE)
    def delete(self, uid: str):
        pass


@namespace.route("/ecosystem/management")
class Management(Resource):
    @namespace.doc(params={**ecosystem_param})
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        response = [api.gaia.get_ecosystem_management(
            db.session, ecosystem
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u/<uid>/management")
class ManagementU(Resource):
    @namespace.doc(params={**no_default(ecosystem_param)})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/management to get more than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        if ecosystem:
            response = api.gaia.get_ecosystem_management(
                db.session, ecosystem[0]
            )
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404


@namespace.route("/ecosystem/sensors_skeleton")
class SensorsSkeleton(Resource):
    @namespace.doc(params={
        **ecosystem_param, **level_param, **time_window_params,
    })
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        level = request.args.get("level", "all")
        time_window = get_time_window_from_request_args()
        response = [api.gaia.get_ecosystem_sensors_data_skeleton(
            db.session, ecosystem, time_window, level
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u/<uid>/sensors_skeleton")
class SensorsSkeletonS(Resource):
    @namespace.doc(params={
        **no_default(ecosystem_param), **level_param, **time_window_params
    })
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/sensors_skeleton to "
                                 "get more than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        level = request.args.get("level", "all")
        time_window = get_time_window_from_request_args()
        if ecosystem:
            response = api.gaia.get_ecosystem_sensors_data_skeleton(
                db.session, ecosystem[0], time_window, level
            )
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404


@namespace.route("/ecosystem/light")
class Light(Resource):
    @namespace.doc(params={**ecosystem_param})
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        response = [api.gaia.get_light_info(
            db.session, ecosystem
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u/<uid>/light")
class LightU(Resource):
    @namespace.doc(params={**no_default(ecosystem_param)})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/light to get more "
                                 "than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        if ecosystem:
            response = api.gaia.get_light_info(db.session, ecosystem[0])
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404


@namespace.route("/ecosystem/environment_parameters")
class EnvironmentParameters(Resource):
    @namespace.doc(params={**ecosystem_param})
    def get(self):
        qs = ecosystem_query_schema.load(request.args)
        ecosystems = ecosystems_or_abort(qs["uid"])
        response = [api.gaia.get_environmental_parameters(
            db.session, ecosystem
        ) for ecosystem in ecosystems]
        return jsonify(response)


@namespace.route("/ecosystem/u/<uid>/environment_parameters")
class EnvironmentParametersU(Resource):
    @namespace.doc(params={**no_default(ecosystem_param)})
    def get(self, uid: str):
        if "all" in uid or len(uid.split(",")) > 1:
            abort(303, {"error": "Use api/gaia/ecosystems/environment_parameters "
                                 "to get more than one ecosystem"})
        ecosystem = ecosystems_or_abort(uid)
        if ecosystem:
            response = api.gaia.get_environmental_parameters(
                db.session, ecosystem[0]
            )
            return jsonify(response)
        return {"error": "Ecosystem not found"}, 404
