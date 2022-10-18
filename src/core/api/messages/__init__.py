from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import api


template_folder = Path(__file__).absolute().parents[0]

loader = FileSystemLoader(template_folder)
environment = Environment(
    loader=loader, lstrip_blocks=True, trim_blocks=True, autoescape=True
)


def replace_underscore(s: str, replacement: str = " ") -> str:
    return s.replace("_", replacement)


environment.filters["replace_underscore"] = replace_underscore


def render_template(rel_path, **context) -> str:
    return environment.get_template(rel_path).render(context)


async def ecosystem_summary(
        session: AsyncSession,
        ecosystems: str | list[str] | None = None
) -> str:
    ecosystem_objs = await api.ecosystem.get_multiple(session, ecosystems)
    ecosystems = [
        api.ecosystem.get_info(session, ecosystem)
        for ecosystem in ecosystem_objs
    ]
    if ecosystems:
        return render_template(
            "telegram/ecosystem.html", ecosystems=ecosystems
        )
    return "No ecosystem found"

"""
def weather(currently: bool = True, forecast: bool = True, **kwargs) -> str:
    weather = {}

    if currently:
        weather["currently"] = api.weather.get_currently()

    if forecast:
        weather["hourly"] = api.weather.summarize_forecast(
            api.weather.get_hourly(12)
        )["forecast"]

        tomorrow = api.weather.get_daily(1)["forecast"][0]
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


def light_info(*ecosystems, session, **kwargs):
    ecosystem_qo = api.ecosystem.get_multiple(
        session=session, ecosystems=ecosystems)
    light_info = api.ecosystem.get_light_info(ecosystem_qo)
    message = render_template(
        "telegram/lights.html", light_info=light_info, **kwargs
    )
    return message


def current_sensors_info(*ecosystems, session):
    raw_sensors = api.ecosystems.get_current_sensors_data_old(
        *ecosystems, session=session)
    sensors = api.ecosystems.summarize_sensors_data(raw_sensors)
    if sensors:
        return api.messages.render_template(
            "telegram/sensors.html", sensors=sensors, units=units)
    return "There is currently no sensors connected"


def recap_sensors_info(*ecosystems, session,
                       days_ago: int = 7):
    window_start = datetime.now()-timedelta(days=days_ago)
    ecosystem_qo = api.ecosystem.get_multiple(
        session=session, ecosystems=ecosystems)
    time_window = api.utils.create_time_window(start=window_start)
    raw_sensors = api.ecosystems._get_ecosystem_historic_sensors_data(
        session, ecosystem_qo, time_window=time_window
    )
    sensors = {e: raw_sensors[e] for e in raw_sensors
               if raw_sensors[e]["data"]}
    avg_sensors = api.ecosystems.average_historic_sensors_data(sensors)
    sum_sensors = api.ecosystems.summarize_sensors_data(avg_sensors)
    return api.messages.render_template(
        "telegram/sensors.html", sensors=sum_sensors, units=units,
        timedelta=days_ago)
"""