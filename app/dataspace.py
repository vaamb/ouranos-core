from threading import Lock

from app.outside import Outside
from app.system_monitor import systemMonitor

lock = Lock()

Outside = Outside()
Outside.start()

systemMonitor = systemMonitor()
systemMonitor.start()

ecosystems_connected = {}
sensorsData = {}
healthData = {}
systemData = {}
