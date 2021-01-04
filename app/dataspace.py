from threading import Lock

from app.system_monitor import systemMonitor


lock = Lock()

sensorsData = {}
healthData = {}
systemData = {}
