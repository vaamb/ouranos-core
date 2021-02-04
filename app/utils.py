from collections import OrderedDict
import os
from pathlib import Path
import socket

import geopy

from config import Config


cache_dir = Path(__file__).absolute().parents[1]/"cache"
if not cache_dir:
    os.mkdir(cache_dir)


class LRU(OrderedDict):
    # Recipe taken from python doc
    def __init__(self, maxsize=32, *args, **kwargs):
        self.maxsize = maxsize
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]


coordinates = LRU(maxsize=16)


def is_connected() -> bool:
    try:
        host = socket.gethostbyname(Config.TEST_CONNECTION_IP)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False


def get_coordinates(city: str) -> dict:
    """
    Memoize and return the geocode of the given city using geopy API. The
    memoization step allows to reduce the number of call to the Nominatim API.

    :param city: str, the name of a city.
    :return: dict with the latitude and longitude of the given city.
    """
    # if not memoized, look for coordinates
    if city not in coordinates:
        geolocator = geopy.geocoders.Nominatim(user_agent="EP-gaia")
        location = geolocator.geocode(city)
        coordinates[city] = {
            "latitude": location.latitude,
            "longitude": location.longitude
        }

    return coordinates[city]
