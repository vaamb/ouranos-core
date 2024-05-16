from datetime import datetime, timezone

from ouranos.core.config.consts import START_TIME


system_dict = {
    "uid": "system_uid",
    "start_time": START_TIME,
    "RAM_total": 1.00,
    "DISK_total": 16.00,
}


system_data_dict = {
    "system_uid": "system_uid",
    "timestamp": datetime.now(timezone.utc),
    "CPU_used": 0.5,
    "CPU_temp": False,
    "RAM_used": 0.25,
    "RAM_process": 0.15,
    "DISK_used": 1.25,
}
