from datetime import datetime, timezone
from threading import Lock

from app.system_monitor import systemMonitor

START_TIME = datetime.now(timezone.utc)

lock = Lock()

sensorsData = {}
healthData = {}
systemData = {}
