from datetime import datetime, time, timedelta, timezone
import logging

from flask import current_app, request
from flask_socketio import join_room, leave_room

from app import app_name, db, scheduler, sio
from app.common.utils import human_delta_time
from app.dataspace import ecosystems_connected, healthData, sensorsData, systemMonitor
from app.models import Data, Ecosystem, Hardware, Health, Light
from config import Config


sio_logger = logging.getLogger(f"{app_name}.socketio")
collector = logging.getLogger(f"{app_name}.collector")

START_TIME = datetime.now(timezone.utc)
SYSTEM_UPDATE_FREQUENCY = 5

_managers = {}
_sid = {}


# ---------------------------------------------------------------------------
#   Background tasks
# ---------------------------------------------------------------------------
@scheduler.scheduled_job(id="sensors_data", trigger="cron", minute="*",
                         misfire_grace_time=10)
def request_sensors_data(room="engineManagers"):
    sio_logger.debug(f"Sending sensors data request to {room}")
    sio.emit("send_sensors_data", namespace="/gaia", room=room)


def request_config(room="engineManagers"):
    sio_logger.debug(f"Sending config request to {room}")
    sio.emit("send_config", namespace="/gaia", room=room)


def request_health_data(room="engineManagers"):
    sio_logger.debug(f"Sending health data request to {room}")
    sio.emit("send_health_data", namespace="/gaia", room=room)


def request_light_data(room="engineManagers"):
    sio_logger.debug(f"Sending light data request to {room}")
    sio.emit("send_light_data", namespace="/gaia", room=room)


@scheduler.scheduled_job(id="light_and_health", trigger="cron",
                         hour="1", misfire_grace_time=15*60)
def request_light_and_health(room="engineManagers"):
    request_light_data(room=room)
    request_health_data(room=room)


def gaia_background_thread(app):
    with app.app_context():
        while True:
            sio.sleep(60)
            for manager in list(_managers.keys()):
                if _managers[manager]["last_seen"] < (datetime.now(timezone.utc) -
                                                      timedelta(minutes=2)):
                    del _managers[manager]
            for ecosystem_uid in list(sensorsData.keys()):
                if sensorsData[ecosystem_uid]["datetime"] < (datetime.now(timezone.utc) -
                                                             timedelta(minutes=4)):
                    pass
                    # TODO: remove ecosystem from sensorsData if not seen for Config.ECOSYSTEM_TIMEOUT


# ---------------------------------------------------------------------------
#   SocketIO events coming from engineManagers
# ---------------------------------------------------------------------------
gaia_thread = None


@sio.on("connect", namespace="/gaia")
def connect_on_gaia():
    global gaia_thread
    if gaia_thread is None:
        gaia_thread = []
        app = current_app._get_current_object()
        gaia_thread.append(sio.start_background_task(gaia_background_thread, app=app))


@sio.on("disconnect", namespace="/gaia")
def disconnect():
    remote_addr = request.environ["REMOTE_ADDR"]
    remote_port = request.environ["REMOTE_PORT"]
    leave_room("engineManagers")
    sio_logger.info(f"disconnect {remote_addr}:{remote_port}")


@sio.on("register_manager", namespace="/gaia")
def registerManager(data):
    remote_addr = request.environ["REMOTE_ADDR"]
    remote_port = request.environ["REMOTE_PORT"]
    sio_logger.info(f"Received manager registration request from manager {data['uid']} " +
                f"from {remote_addr}:{remote_port}")
    _managers.update(
        {data["uid"]: {"sid": request.sid,
                       "last_seen": datetime.now(timezone.utc),
                       }}
    )
    _sid.update({request.sid: data["uid"]})
    join_room("engineManagers")
    request_config(request.sid)
    request_sensors_data(request.sid)
    request_light_data(request.sid)
    request_health_data(request.sid)


@sio.on("engines_change", namespace="/gaia")
def reload_all():
    request_config(request.sid)
    request_sensors_data(request.sid)
    request_light_data(request.sid)
    request_health_data(request.sid)


@sio.on("config", namespace="/gaia")
def update_cfg(config):
    try:
        manager_uid = _sid[request.sid]
    except KeyError:
        sio.emit("register", namespace="/gaia", room=request.sid)
        return False
    sio_logger.debug(f"Received 'config' from {manager_uid}")
    for ecosystem_id in config:
        ecosystems_connected.update({ecosystem_id: {"manager_uid": manager_uid,
                                                    "name": config[ecosystem_id]["name"]}})
        ecosystem = Ecosystem(
            id=ecosystem_id,
            name=config[ecosystem_id]["name"],
            status=config[ecosystem_id]["status"],
            lighting=config[ecosystem_id]["management"]["lighting"],
            watering=config[ecosystem_id]["management"]["watering"],
            climate=config[ecosystem_id]["management"]["climate"],
            health=config[ecosystem_id]["management"]["health"],
            alarms=config[ecosystem_id]["management"]["alarms"],
            webcam=config[ecosystem_id]["webcam"].get("model", "No"),
            day_start=datetime.strptime(config[ecosystem_id]["environment"]["day"]["start"], "%Hh%M").time(),
            day_temperature=config[ecosystem_id]["environment"]["day"]["temperature"]["target"],
            day_humidity=config[ecosystem_id]["environment"]["day"]["humidity"]["target"],
            night_start=datetime.strptime(config[ecosystem_id]["environment"]["night"]["start"], "%Hh%M").time(),
            night_temperature=config[ecosystem_id]["environment"]["night"]["temperature"]["target"],
            night_humidity=config[ecosystem_id]["environment"]["night"]["humidity"]["target"],
            temperature_hysteresis=config[ecosystem_id]["environment"]["hysteresis"]["temperature"],
            humidity_hysteresis=config[ecosystem_id]["environment"]["hysteresis"]["humidity"]
        )
        db.session.merge(ecosystem)
        #TODO: first delete all hardware present there before, so if delete in config, deleted here too
        for hardware_id in config[ecosystem_id]["IO"]:
            hardware = Hardware(
                id=hardware_id,
                ecosystem_id=ecosystem_id,
                name=config[ecosystem_id]["IO"][hardware_id]["name"],
                pin=config[ecosystem_id]["IO"][hardware_id]["pin"],
                type=config[ecosystem_id]["IO"][hardware_id]["type"],
                level=config[ecosystem_id]["IO"][hardware_id]["level"],
                model=config[ecosystem_id]["IO"][hardware_id]["model"]
            )
            db.session.merge(hardware)
    db.session.commit()


@sio.on("sensors_data", namespace="/gaia")
def update_sensors_data(data):
    manager_uid = _sid[request.sid]
    _managers[manager_uid]["last_seen"] = datetime.now(timezone.utc)
    # TODO: move the last seen in a ping-pong
    sio_logger.debug(f"Received 'sensors_data' from {manager_uid}")
    sensorsData.update(data)
    for ecosystem_id in data:
        dt = datetime.fromisoformat(data[ecosystem_id]["datetime"])
        sensorsData[ecosystem_id]["datetime"] = dt
        if dt.minute % Config.SENSORS_LOGGING_FREQUENCY == 0:
            collector.debug("Logging sensors data from enginesManager " +
                            f"{manager_uid}")
            for sensor_id in data[ecosystem_id]["data"]:
                for measure in data[ecosystem_id]["data"][sensor_id]:
                    sensor = Data(
                        ecosystem_id=ecosystem_id,
                        sensor_id=sensor_id,
                        measure=measure,
                        datetime=dt,
                        value=data[ecosystem_id]["data"][sensor_id][measure],
                    )
                    db.session.add(sensor)
    db.session.commit()


@sio.on("health_data", namespace="/gaia")
def update_health_data(data):
    manager_uid = _sid[request.sid]
    sio_logger.debug(f"Received 'update_health_data' from {manager_uid}")
    healthData.update(data)
    for ecosystem_id in data:
        health = Health(
            ecosystem_id=ecosystem_id,
            datetime=datetime.fromisoformat(data[ecosystem_id]["datetime"]),
            green=data[ecosystem_id]["green"],
            necrosis=data[ecosystem_id]["necrosis"],
            health_index=data[ecosystem_id]["health_index"]
        )
        db.session.add(health)
    db.session.commit()


@sio.on("light_data", namespace="/gaia")
def update_light_data(data):
    manager_uid = _sid[request.sid]
    sio_logger.debug(f"Received 'light_data' from {manager_uid}")
    for ecosystem_id in data:
        if data[ecosystem_id].get("lighting_hours"):
            morning_start = time.fromisoformat(data[ecosystem_id]["lighting_hours"]["morning_start"])
            morning_end = time.fromisoformat(data[ecosystem_id]["lighting_hours"]["morning_end"])
            evening_start = time.fromisoformat(data[ecosystem_id]["lighting_hours"]["evening_start"])
            evening_end = time.fromisoformat(data[ecosystem_id]["lighting_hours"]["evening_end"])
        else:
            morning_start = morning_end = evening_start = evening_end = None
        light = Light(
            ecosystem_id=ecosystem_id,
            status=data[ecosystem_id]["status"],
            mode=data[ecosystem_id]["mode"],
            method=data[ecosystem_id]["method"],
            morning_start=morning_start,
            morning_end=morning_end,
            evening_start=evening_start,
            evening_end=evening_end
        )
        db.session.merge(light)
    db.session.commit()


# ---------------------------------------------------------------------------
#   SocketIO events coming from browser clients
# ---------------------------------------------------------------------------
browser_thread = None


def get_manager_sid(ecosystem_id):
    manager_uid = ecosystems_connected[ecosystem_id]["manager_uid"]
    manager_sid = _managers[manager_uid]["sid"]
    return manager_sid


# TODO: send sensors data in real time
def browser_background_thread(app):
    with app.app_context():
        global sensorsData
        while True:
            data = {**sensorsData,
                    }
            sio.emit("currentData", "data", namespace="/browser")
            sio.sleep(3)


@sio.on("connect", namespace="/browser")
def connect_on_browser():
    global browser_thread
    if browser_thread is None:
        app = current_app._get_current_object()
        browser_thread = sio.start_background_task(browser_background_thread, app=app)


@sio.on("request_server_data", namespace="/browser")
def send_server_data():
    global systemMonitor
    incoming_sid = request.sid
    data = dict(systemMonitor.system_data)
    del data["datetime"]
    data.update({"uptime": human_delta_time(START_TIME, datetime.now(timezone.utc))})
    sio.emit("server_data", data, namespace="/browser", room=incoming_sid)


@sio.on("my_ping", namespace="/browser")
def ping_pong():
    incoming_sid = request.sid
    sio.emit("my_pong", namespace="/browser", room=incoming_sid)


@sio.on("turn_light_on", namespace="/browser")
def turn_light_on(message):
    ecosystem_id = message["ecosystem"]
    countdown = message.get("countdown", False)
    sio_logger.debug(f"Dispatching 'turn_light_on' signal to ecosystem {ecosystem_id}")
    sid = get_manager_sid(ecosystem_id)
    sio.emit("turn_light_on", {"ecosystem": ecosystem_id, "countdown": countdown},
             namespace="/gaia", room=sid)
    return False


@sio.on("turn_light_off", namespace="/browser")
def turn_light_off(message):
    ecosystem_id = message["ecosystem"]
    countdown = message.get("countdown", False)
    sio_logger.debug(f"Dispatching 'turn_light_off' signal to ecosystem {ecosystem_id}")
    sid = get_manager_sid(ecosystem_id)
    sio.emit("turn_light_off", {"ecosystem": ecosystem_id, "countdown": countdown},
             namespace="/gaia", room=sid)
    return False


@sio.on("turn_light_auto", namespace="/browser")
def turn_light_auto(message):
    ecosystem_id = message["ecosystem"]
    sio_logger.debug(f"Dispatching 'turn_light_auto' signal to ecosystem {ecosystem_id}")
    sid = get_manager_sid(ecosystem_id)
    sio.emit("turn_light_auto", {"ecosystem": ecosystem_id}, namespace="/gaia", room=sid)
    return False

