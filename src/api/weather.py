from collections import Counter
from datetime import datetime, time, timedelta, timezone

from statistics import mean

from src.cache import weatherData, sunTimesData
from src.consts import WEATHER_MEASURES
from src.utils import parse_sun_times


def _get_time_of_day(dt_time: time) -> str:
    if dt_time < time(7, 0):
        return "night"
    elif time(7, 0) <= dt_time <= time(12, 0):
        return "morning"
    elif time(12, 0) < dt_time <= time(18, 30):
        return "afternoon"
    elif time(18, 30) < dt_time:
        return "evening"


def mode(iterable) -> str:
    return Counter(iterable).most_common()[0][0]


# Current weather
def get_current_weather() -> dict:
    return weatherData.get("currently", {})


# Weather forecast
def get_forecast(time_unit: str, time_window: int) -> dict:
    data = weatherData.get(time_unit)
    if data:
        if time_window > len(data["forecast"]):
            time_window = len(data["forecast"]) - 1
        forecast = [data["forecast"][_] for _ in range(time_window)]
        return {
            "time_window": {
                "start": forecast[0]["time"],
                "end": forecast[time_window - 1]["time"]
            },
            "forecast": forecast,
        }
    return {}


def get_hourly_weather_forecast(time_window: int = 24) -> dict:
    return get_forecast("hourly", time_window)


def get_daily_weather_forecast(time_window: int = 7,
                               skip_today: bool = True) -> dict:
    data = get_forecast("daily", time_window)
    if skip_today:
        del data["forecast"][0]
    return data


def summarize_forecast(forecast: dict) -> dict:
    digest = {}
    result = {}
    data = forecast["forecast"]
    for elem in data:
        for info in WEATHER_MEASURES["mode"] + WEATHER_MEASURES["mean"]:
            try:
                d = elem[info]
            except KeyError:
                continue
            if digest.get(info):
                digest[info].append(d)
            else:
                digest[info] = [d]

    for info in digest:
        if info in WEATHER_MEASURES["mode"]:
            result[info] = mode(digest[info])
        elif info in WEATHER_MEASURES["mean"]:
            result[info] = mean(digest[info])
        if info in WEATHER_MEASURES["range"]:
            result[f"{info}High"] = max(digest[info])
            result[f"{info}Low"] = min(digest[info])

    return {
        "time_window": forecast["time_window"],
        "forecast": result,
    }


def _digest_hourly_weather_forecast(weather_forecast: dict) -> dict:
    if weather_forecast:
        now = datetime.now(timezone.utc)
        digest = {}
        for hour in weather_forecast["forecast"]:
            tod = _get_time_of_day(hour["datetime"].time())
            time_limits = {
                "today": now.date(),
                "tomorrow": now.date() + timedelta(days=1),
                "day_after_tomorrow": now.date() + timedelta(days=2),
            }
            for time_limit in time_limits:
                if hour["datetime"].date() == time_limits[time_limit]:
                    day = time_limit
                    try:
                        digest[day]
                    except KeyError:
                        digest[day] = {}
                    break

            try:
                digest[day][tod]
            except KeyError:
                digest[day][tod] = {}

            for info in WEATHER_MEASURES["mean"] + WEATHER_MEASURES["mode"]:
                try:
                    digest[day][tod][info].append(hour["weather"][info])
                except KeyError:
                    digest[day][tod].update({info: [hour["weather"][info]]})

        return {
            "time_window": weather_forecast["time_window"],
            "forecast": digest,
        }
    return {}


def _summarize_digested_weather_forecast(digested_weather_forecast: dict) -> dict:
    if digested_weather_forecast:
        summary = {
            "time_window": digested_weather_forecast["time_window"],
            "forecast": {}
        }

        for day in digested_weather_forecast["forecast"]:
            day_forecast = digested_weather_forecast["forecast"][day]
            summary["forecast"][day] = {}

            for tod in day_forecast:
                summary["forecast"][day][tod] = {}

                for info in WEATHER_MEASURES["mode"]:
                    summary["forecast"][day][tod][info] = \
                        mode(day_forecast[tod][info])[0]

                for info in WEATHER_MEASURES["mean"]:
                    summary["forecast"][day][tod][info] = \
                        round(mean(day_forecast[tod][info]), 1)

        return digested_weather_forecast
    return {}


def get_digested_hourly_weather_forecast(time_window: int = 24) -> dict:
    forecast = get_hourly_weather_forecast(time_window=time_window)
    digest = _digest_hourly_weather_forecast(forecast)
    summary = _summarize_digested_weather_forecast(digest)
    return summary


def get_suntimes_data() -> dict:
    return {
        event: parse_sun_times(sunTimesData[event]) for event in sunTimesData
        if event != "day_length"
    }
