import os
from pathlib import Path
import socket

from config import Config


cache_dir = Path(__file__).absolute().parents[1]/"cache"
if not cache_dir:
    os.mkdir(cache_dir)


def is_connected():
    try:
        host = socket.gethostbyname(Config.TEST_CONNECTION_IP)
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except Exception as ex:
        print(ex)
    return False
