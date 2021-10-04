from flask import request, jsonify
from flask_restx import Namespace, Resource

from src.app import API, db


namespace = Namespace(
    "system",
    description="Information about the system. Rem: it is required to be "
                "logged in to access data.",
)


@namespace.route("/current_data")
@namespace.hide
class CurrentData(Resource):
    def get(self):
        response = API.admin.get_current_system_data()
        return jsonify(response)


@namespace.route("/data")
@namespace.hide
class Data(Resource):
    def get(self):
        historic_system_data = API.admin.get_historic_system_data(db.session)
        return jsonify(historic_system_data)
