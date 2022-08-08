from flask import abort, request, jsonify
from flask_restx import Resource

from . import namespace
from ..api_doc import manager_param, engines_query_schema, no_default
from ..decorators import permission_required
from src import api
from src.app import db
from src.database.models.app import Permission


@namespace.route("/engine")
class Manager(Resource):
    @namespace.doc(params={**manager_param})
    def get(self):
        qs = engines_query_schema.load(request.args)
        engines = api.gaia.get_engines(db.session, qs["uid"])
        response = [api.gaia.get_engine_info(
            db.session, engine
        ) for engine in engines]
        return jsonify(response)


@namespace.route("/engine/u/<uid>")
class ManagerU(Resource):
    @namespace.doc(params={**no_default(manager_param)})
    def get(self, uid: str):
        engine = api.gaia.get_engines(db.session, uid)
        if engine:
            response = api.gaia.get_engine_info(db.session, engine[0])
            return jsonify(response)
        return {"error": "Engine not found"}, 404

    @namespace.doc(params={**no_default(manager_param)})
    @permission_required(Permission.OPERATE)
    def put(self, uid: str):
        pass

    @namespace.doc(params={**no_default(manager_param)})
    @permission_required(Permission.OPERATE)
    def delete(self, uid: str):
        pass
