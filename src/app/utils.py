from __future__ import annotations

import base64
import os
import platform

import cachetools
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import geopy

from config import Config


app_config: dict[str, str | int] = {}


coordinates = cachetools.LFUCache(maxsize=16)


def set_app_config(config: dict):
    global app_config
    app_config = config


def arg_to_bool(arg: bool | int | str) -> bool:
    if isinstance(arg, bool):
        return arg
    if isinstance(arg, int):
        return bool(arg)
    if arg.lower() == "true":
        return True
    elif arg.lower() == "false":
        return False
    raise ValueError("string must be 1, 0, 'true' or 'false'")


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


def decrypt_uid(encrypted_uid: str) -> str:
    h = hashes.Hash(hashes.SHA256())
    h.update(Config.GAIA_SECRET_KEY.encode("utf-8"))
    key = base64.urlsafe_b64encode(h.finalize())
    f = Fernet(key=key)
    try:
        return f.decrypt(encrypted_uid.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def validate_uid_token(token: str, manager_uid: str) -> bool:
    iterations = int(token.split("$")[0].split(":")[2])
    ssalt = token.split("$")[1]
    token_key = token.split("$")[2]
    bsalt = ssalt.encode("UTF-8")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=bsalt,
        iterations=iterations,
    )
    bkey = kdf.derive(manager_uid.encode())
    hkey = base64.b64encode(bkey).hex()
    return token_key == hkey


def generate_secret_key_from_password(password: str, set_env: bool = False) -> str:
    if isinstance(password, str):
        password = password.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"",
        iterations=2**21,
    )
    bkey = kdf.derive(password)
    skey = base64.b64encode(bkey).decode("utf-8").strip("=")
    if set_env:
        if platform.system() in ("Linux", "Windows"):
            os.environ["GAIA_SECRET_KEY"] = skey
        else:
            # Setting environ in BSD and MacOsX can lead to mem leak (cf. doc)
            os.putenv("GAIA_SECRET_KEY", skey)
    return skey
