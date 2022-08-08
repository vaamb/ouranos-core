from flask import jsonify
from flask_restx import Namespace, Resource

from .decorators import permission_required
from .utils import get_time_window_from_request_args
from src import api
from src.app import db
from src.database.models.app import Permission


namespace = Namespace(
    "system",
    description="Information about the system. Rem: it is required to be "
                "logged in to access data.",
)


@namespace.route("/current_data")
class CurrentData(Resource):
    @namespace.doc(security="cookie_auth")
    @permission_required(Permission.ADMIN)
    def get(self):
        response = api.admin.get_current_system_data()
        return jsonify(response)


@namespace.route("/data")
class Data(Resource):
    @namespace.doc(security="cookie_auth")
    @permission_required(Permission.ADMIN)
    def get(self):
        time_window = get_time_window_from_request_args()
        historic_system_data = api.admin.get_historic_system_data(
            db.session, time_window
        )
        return jsonify(historic_system_data)
