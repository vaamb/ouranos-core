from flask import current_app, jsonify, request
from flask_restx import Namespace, Resource

from .decorators import permission_required
from src import api
from src.app import db
from src.database.models.app import Permission


namespace = Namespace(
    "app",
    description="Information about the app",
)


@namespace.route("/version")
class Version(Resource):
    def get(self):
        return jsonify(current_app.config.get("VERSION"))


@namespace.route("/logging_period")
class LoggingConfig(Resource):
    def get(self):
        return jsonify({
            "weather": current_app.config.get("OURANOS_WEATHER_UPDATE_PERIOD", None),
            "system": current_app.config.get("SYSTEM_LOGGING_PERIOD", None),
            "sensors": current_app.config.get("SENSORS_LOGGING_PERIOD", None),
        })


@namespace.route("/services")
class Functionalities(Resource):
    def get(self):
        level = request.args.get("level", "all").split(",")
        response = api.app.get_services(session=db.session, level=level)
        return jsonify(response)


# TODO: for future use
@namespace.route("/flash_message")
class FlashMessage(Resource):
    def get(self):
        response = {}
        return jsonify(response)


@namespace.route("/warnings")
class Warnings(Resource):
    @permission_required(Permission.VIEW)
    def get(self):
        response = api.warnings.get_recent_warnings(db.session, limit=8)
        return jsonify(response)
