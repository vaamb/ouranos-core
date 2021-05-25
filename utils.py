from datetime import date, datetime, timezone
from pathlib import Path
import socket


base_dir = Path(__file__).absolute().parents[0]


def is_connected(ip_to_connect="1.1.1.1") -> bool:
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
