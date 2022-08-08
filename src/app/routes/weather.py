from flask import request, jsonify
from flask_restx import Namespace, Resource

from src import api


namespace = Namespace(
    "weather",
    description="Information about the weather. Rem: it returns data only if "
                "the weather service has been enabled.",
)


@namespace.route("/sun_times")
class SunTimes(Resource):
    def get(self):
        response = api.weather.get_suntimes_data()
        return jsonify(response)


@namespace.route("/forecast")
class Forecast(Resource):
    def get(self):
        exclude = request.args.get("exclude", "").split(",")
        # exclude can be current, hourly or daily
        response = {}
        if "currently" not in exclude:
            response.update({
                "currently": api.weather.get_current_weather()
            })
        if "hourly" not in exclude:
            response.update({
                "hourly": api.weather.get_hourly_weather_forecast()
            })
        if "daily" not in exclude:
            response.update({
                "daily": api.weather.get_daily_weather_forecast()
            })
        return jsonify(response)


@namespace.route("/forecast/currently")
class Current(Resource):
    def get(self):
        response = api.weather.get_current_weather()
        return jsonify(response)


@namespace.route("/forecast/hourly")
class Hourly(Resource):
    def get(self):
        response = api.weather.get_hourly_weather_forecast()
        return jsonify(response)


@namespace.route("/forecast/daily")
class Daily(Resource):
    def get(self):
        response = api.weather.get_daily_weather_forecast()
        return jsonify(response)
