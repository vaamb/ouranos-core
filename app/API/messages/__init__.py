from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app import API

template_folder = Path(__file__).absolute().parents[0]

loader = FileSystemLoader(template_folder)
environment = Environment(loader=loader, lstrip_blocks=True, trim_blocks=True)


def render_template(rel_path, **context):
    return environment.get_template(rel_path).render(context)


def weather(currently: bool = True, forecast: bool = True) -> str:
    weather = {}

    if currently:
        weather["currently"] = API.weather.get_current_weather()

    if forecast:
        weather["hourly"] = API.weather.summarize_forecast(
            API.weather.get_hourly_weather_forecast(12)
        )["forecast"]

        tomorrow = API.weather.get_daily_weather_forecast(1)["forecast"][0]
        sunrise = datetime.fromtimestamp(tomorrow["sunriseTime"])
        tomorrow["sunriseTime"] = sunrise.strftime("%H:%M")
        sunset = datetime.fromtimestamp(tomorrow["sunsetTime"])
        tomorrow["sunsetTime"] = sunset.strftime("%H:%M")
        length = (sunset - sunrise).seconds
        hours = length // 3600
        minutes = (length % 3600) // 60
        tomorrow["dayLength"] = f"{hours}:{minutes}"
        weather["tomorrow"] = tomorrow

    return render_template(
        "telegram/weather.html", weather=weather
    )


def light_info(*ecosystems, session):
    ecosystem_qo = API.ecosystems.get_ecosystem_query_obj(
        ecosystems, session=session)
    light_info = API.ecosystems.get_light_info(ecosystem_qo)
    message = render_template(
        "telegram/lights.html", light_info=light_info
    )
    return message
