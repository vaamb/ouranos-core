from datetime import date, datetime, timezone
from pathlib import Path
import socket

from flask import json
from sqlalchemy.engine import Row


base_dir = Path(__file__).absolute().parents[0]


def is_connected(ip_to_connect: str = "1.1.1.1") -> bool:
    try:
        host = socket.gethostbyname(ip_to_connect)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False


def parse_sun_times(moment: str) -> datetime:
    _time = datetime.strptime(moment, "%I:%M:%S %p").time()
    return datetime.combine(date.today(), _time,
                            tzinfo=timezone.utc)


def config_dict_from_class(obj) -> dict:
    config = {}
    for key in dir(obj):
        if key.isupper():
            config[key] = getattr(obj, key)
    return config


class customJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Row):
            # return {**o._mapping}  # return a dict
            return o._data  # return a tuple
        return super(customJSONEncoder, self).default(o)


class jsonWrapper:
    @staticmethod
    def dumps(*args, **kwargs):
        if 'cls' not in kwargs:
            kwargs['cls'] = customJSONEncoder
        return json.dumps(*args, **kwargs)

    @staticmethod
    def loads(*args, **kwargs):
        return json.loads(*args, **kwargs)
