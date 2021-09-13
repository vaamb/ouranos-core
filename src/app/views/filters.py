from datetime import datetime
from hashlib import sha1

from cachetools import cached, TTLCache
from flask import Blueprint
from jinja2 import Markup
from sqlalchemy.engine import Row

from src.utils import humanize_list, json

try:
    import orjson as _json

    def row_dumps(o):
        if isinstance(o, Row):
            return o._data
        raise TypeError(f"Object of type {o.__class__.__name__} "
                        f"is not JSON serializable")

    def json_dumps(o) -> str:
        return _json.dumps(o, default=row_dumps,
                           option=_json.OPT_NAIVE_UTC).decode("utf-8")


except ImportError:
    # orjson is not available on 32 bits systems
    _json = json

    def json_dumps(o) -> str:
        return _json.dumps(o)


bp = Blueprint("base", __name__)
fast_json_cache = TTLCache(maxsize=32, ttl=900)


@bp.app_template_filter("fast_json")
def fast_json(o) -> str:
    time_window = o.get("time_window", {})

    @cached(fast_json_cache)
    def memoizing_func(name, start, end, level) -> str:
        # If orjson is available, uses it
        # return same results as flask.json.tojson_filter()
        return Markup(json_dumps(o)
                      .replace(u"<", u"\\u003c")
                      .replace(u">", u"\\u003e")
                      .replace(u"&", u"\\u0026")
                      .replace(u"'", u"\\u0027")
                      )

    return memoizing_func(
        name=o.get("name"), start=time_window.get("start"),
        end=time_window.get("end"), level=o.get("level"),
    )


@bp.app_template_filter("removeUnderscores")
def replace_underscore(s: str, replacement: str = " ") -> str:
    return s.replace("_", replacement)


@bp.app_template_filter("getDay")
def get_day(s: float) -> str:
    return datetime.fromtimestamp(s).strftime("%A %d %B")


@bp.app_template_filter("getTime")
def get_time(s: float) -> str:
    x = datetime.fromtimestamp(s)
    return f"{x.hour}:{x.minute :02d}"  # somehow, use .strftime("%H:%S") returns the same value for the whole page


@bp.app_template_filter("getWeatherIcon")
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


@bp.app_template_filter("humanizeList")
def _humanize_list(lst: list) -> str:
    return humanize_list(lst)


@bp.app_template_filter("roundDecimals")
def round_to_decimals(x: float) -> float:
    rounded = round(x, 1)
    return rounded  # "{:.1f}".format(rounded)


@bp.app_template_filter("tryKeys")
def try_dict(dct: dict, key: str) -> str:
    try:
        return dct[key]
    except KeyError:
        return ""


@bp.app_template_filter("toJSBool")
def _translate_to_JS_bool(python_bool: bool) -> str:
    if python_bool:
        return "true"
    else:
        return "false"


@bp.app_template_filter("hash")
def _hash(str_to_hash: str) -> str:
    byte_to_hash = str_to_hash.encode()
    h = sha1()
    h.update(byte_to_hash)
    return h.hexdigest()