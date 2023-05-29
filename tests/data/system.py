from datetime import datetime, timezone


system_dict = {
    "system_uid": "system_uid",
    "timestamp": datetime.now(timezone.utc),
    "CPU_used": 0.5,
    "CPU_temp": False,
    "RAM_total": 1.00,
    "RAM_used": 0.25,
    "RAM_process": 0.15,
    "DISK_total": 16.00,
    "DISK_used": 1.25,
}
