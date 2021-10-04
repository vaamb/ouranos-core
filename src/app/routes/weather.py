from flask import request, jsonify
from flask_restx import Namespace, Resource

from src.app import API, db


namespace = Namespace(
    "weather",
    description="Information about the weather. Rem: it returns data only if "
                "the weather service has been enabled.",
)


@namespace.route("/sun_times")
class SunTimes(Resource):
    def get(self):
        response = API.weather.get_suntimes_data()
        return jsonify(response)


@namespace.route("/forecast")
class Forecast(Resource):
    def get(self):
        exclude = request.args.get("exclude").split(",")
        # exclude can be current, hourly daily
        # TODO
