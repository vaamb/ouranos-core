from datetime import datetime
from hashlib import sha1

from app.utils import humanize_list
from app.views.main import bp


@bp.app_template_filter('removeUnderscores')
def replace_underscore(s: str, replacement: str = " ") -> str:
    return s.replace("_", replacement)


@bp.app_template_filter('getDay')
def get_day(s: float) -> str:
    return datetime.fromtimestamp(s).strftime("%A %d %B")


@bp.app_template_filter('getTime')
def get_time(s: float) -> str:
    x = datetime.fromtimestamp(s)
    return f"{x.hour}:{x.minute :02d}"  # somehow, use .strftime("%H:%S") returns the same value for the whole page


@bp.app_template_filter('getWeatherIcon')
def get_weather_icon(weather: str) -> str:
    translation = {"clear-day": "wi wi-day-sunny",
                   "clear-night": "wi wi-night-clear",
                   "rain": "wi wi-rain",
                   "snow": "wi wi-snow",
                   "sleet": "wi wi-sleet",
                   "wind": "wi wi-cloudy-gusts",
                   "fog": "wi wi-fog",
                   "cloudy": "wi wi-cloudy",
                   "partly-cloudy-day": "wi wi-day-cloudy",
                   "partly-cloudy-night": "wi wi-night-alt-cloudy",
                   }
    return translation[weather]


@bp.app_template_filter('humanizeList')
def _humanize_list(lst: list) -> str:
    return humanize_list(lst)


@bp.app_template_filter('roundDecimals')
def round_to_decimals(x: float) -> float:
    rounded = round(x, 1)
    return rounded  # "{:.1f}".format(rounded)


@bp.app_template_filter('tryKeys')
def try_dict(dct: dict, key: str) -> str:
    try:
        return dct[key]
    except KeyError:
        return ""


@bp.app_template_filter('toJSBool')
def _translate_to_JS_bool(python_bool: bool) -> str:
    if python_bool:
        return "true"
    else:
        return "false"


@bp.app_template_filter('hash')
def _hash(str_to_hash: str) -> str:
    byte_to_hash = str_to_hash.encode()
    h = sha1()
    h.update(byte_to_hash)
    return h.hexdigest()
