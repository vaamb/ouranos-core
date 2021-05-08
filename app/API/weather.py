from datetime import datetime, time, timedelta, timezone

from numpy import mean
from scipy.stats import mode

from app.API import app
from app.API.utils import get_service
from app.utils import parse_sun_times


weather_measures = {
    "mean": ["temperature", "temperatureLow", "temperatureHigh", "humidity",
             "windSpeed", "cloudCover", "precipProbability", "dewPoint"],
    "mode": ["summary", "icon"],
    "other": ["time", "sunriseTime", "sunsetTime"],
}

weather_data_multiplication_factors = {
    "temperature": 1,
    "humidity": 100,
    "windSpeed": 1,
    "cloudCover": 100,
    "precipProbability": 100,
}


def _weather_on():
    try:
        return get_service("weather").status
    except RuntimeError:
        return False


def _get_time_of_day(dt_time: time):
    if dt_time < time(7, 0):
        return "night"
    elif time(7, 0) <= dt_time <= time(12, 0):
        return "morning"
    elif time(12, 0) < dt_time <= time(18, 30):
        return "afternoon"
    elif time(18, 30) < dt_time:
        return "evening"


# Current weather
def get_current_weather():
    if _weather_on():
        return get_service("weather").current_data
    return {}


# Weather forecast
def get_forecast(unit, time_window):
    if _weather_on():
        data = get_service("weather").data[unit]
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


def get_hourly_weather_forecast(time_window=24):
    return get_forecast("hourly", time_window)


def get_daily_weather_forecast(time_window=7):
    return get_forecast("daily", time_window)


def _digest_hourly_weather_forecast(weather_forecast) -> dict:
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

            for info in weather_measures["mean"] + weather_measures["mode"]:
                try:
                    digest[day][tod][info].append(hour["weather"][info])
                except KeyError:
                    digest[day][tod].update({info: [hour["weather"][info]]})

        return {
            "time_window": weather_forecast["time_window"],
            "forecast": digest,
        }
    return {}


def _summarize_digested_weather_forecast(digested_weather_forecast):
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

                for info in weather_measures["mode"]:
                    summary["forecast"][day][tod][info] = \
                        mode(day_forecast[tod][info])[0]

                for info in weather_measures["mean"]:
                    summary["forecast"][day][tod][info] = \
                        round(mean(day_forecast[tod][info]), 1)

        return digested_weather_forecast
    return {}


def get_summarized_hourly_weather_forecast(time_window=24):
    forecast = get_hourly_weather_forecast(time_window=time_window)
    digest = _digest_hourly_weather_forecast(forecast)
    summary = _summarize_digested_weather_forecast(digest)
    return summary


def get_suntimes_data():
    suntimes_service = get_service("sun_times")
    suntimes = suntimes_service.get_data()
    return {event: parse_sun_times(suntimes[event]) for event in suntimes
            if event != "day_length"}
