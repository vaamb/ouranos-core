from datetime import datetime, time, timezone
import logging

from flask import current_app, request
from flask_socketio import join_room, leave_room
from numpy import mean, std

from app import app_name, db, scheduler, sio
from app.views.views_utils import human_delta_time
from app.dataspace import healthData, sensorsData, systemMonitor, START_TIME
from app.models import sensorData, Ecosystem, engineManager, Hardware, Health, Light
from config import Config


sio_logger = logging.getLogger(f"{app_name}.socketio")
collector = logging.getLogger(f"{app_name}.collector")

SYSTEM_UPDATE_FREQUENCY = 5

# Temporary anchors to keep PyCharm to delete these from import
anchor1 = sensorsData
anchor2 = systemMonitor

summarize = {"mean": mean, "std": std}


# TODO: add events from views.admin here

# ---------------------------------------------------------------------------
#   Data requests to engineManagers
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
            sio.emit("ping", namespace="/gaia", room="engineManagers")
            sio.sleep(15)


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
        gaia_thread.append(sio.start_background_task(
            gaia_background_thread, app=app))


@sio.on("disconnect", namespace="/gaia")
def disconnect():
    remote_addr = request.environ["REMOTE_ADDR"]
    remote_port = request.environ["REMOTE_PORT"]
    leave_room("engineManagers")
    sio_logger.info(f"disconnect {remote_addr}:{remote_port}")


@sio.on("pong", namespace="/gaia")
def gaia_pong(data):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    manager = engineManager.query.filter_by(sid=request.sid).one()
    manager.last_seen = now
    for ecosystem_uid in data:
        ecosystem = Ecosystem.query.filter_by(id=ecosystem_uid).one()
        ecosystem.last_seen = now
    db.session.commit()


@sio.on("register_manager", namespace="/gaia")
def registerManager(data):
    remote_addr = request.environ["REMOTE_ADDR"]
    remote_port = request.environ["REMOTE_PORT"]
    sio_logger.info(f"Received manager registration request from manager: "
                    f"{data['uid']}, with address {remote_addr}:{remote_port}")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    manager = engineManager(
        uid=data["uid"],
        sid=request.sid,
        last_seen=now,
        address=f"{remote_addr}:{remote_port}",
    )
    db.session.merge(manager)
    db.session.commit()
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
    manager = engineManager.query.filter_by(sid=request.sid).one()
    if not manager:
        sio.emit("register", namespace="/gaia", room=request.sid)
        return False
    sio_logger.debug(f"Received 'config' from {manager.uid}")
    for ecosystem_id in config:
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
            day_start=datetime.strptime(
                config[ecosystem_id]["environment"]["day"]["start"], "%Hh%M"
            ).time(),
            day_temperature=config[ecosystem_id]["environment"]["day"]["temperature"]["target"],
            day_humidity=config[ecosystem_id]["environment"]["day"]["humidity"]["target"],
            night_start=datetime.strptime(
                config[ecosystem_id]["environment"]["night"]["start"], "%Hh%M"
            ).time(),
            night_temperature=config[ecosystem_id]["environment"]["night"]["temperature"]["target"],
            night_humidity=config[ecosystem_id]["environment"]["night"]["humidity"]["target"],
            temperature_hysteresis=config[ecosystem_id]["environment"]["hysteresis"]["temperature"],
            humidity_hysteresis=config[ecosystem_id]["environment"]["hysteresis"]["humidity"],
            manager_uid=manager.uid,
        )
        db.session.merge(ecosystem)

        # TODO: first delete all hardware present there before, so if delete in config, deleted here too
        for hardware_id in config[ecosystem_id]["IO"]:
            hardware = Hardware(
                id=hardware_id,
                ecosystem_id=ecosystem_id,
                name=config[ecosystem_id]["IO"][hardware_id]["name"],
                address=config[ecosystem_id]["IO"][hardware_id]["address"],
                type=config[ecosystem_id]["IO"][hardware_id]["type"],
                level=config[ecosystem_id]["IO"][hardware_id]["level"],
                model=config[ecosystem_id]["IO"][hardware_id]["model"],
            )
            db.session.merge(hardware)
    db.session.commit()


@sio.on("sensors_data", namespace="/gaia")
def update_sensors_data(data):
    # TODO: try manager = ... if error: register
    manager = engineManager.query.filter_by(sid=request.sid).one()
    sio_logger.debug(f"Received 'sensors_data' from manager: {manager.uid}")
    sensorsData.update(data)
    for ecosystem_id in data:
        dt = datetime.fromisoformat(data[ecosystem_id]["datetime"])
        sensorsData[ecosystem_id]["datetime"] = dt
        if dt.minute % Config.SENSORS_LOGGING_FREQUENCY == 0:
            measure_values = {}
            collector.debug(f"Logging sensors data from manager: {manager.uid}")
            for sensor_id in data[ecosystem_id]["data"]:
                for measure in data[ecosystem_id]["data"][sensor_id]:
                    value = float(data[ecosystem_id]["data"][sensor_id][measure])
                    sensor_data = sensorData(
                        ecosystem_id=ecosystem_id,
                        sensor_id=sensor_id,
                        measure=measure,
                        datetime=dt,
                        value=value,
                    )
                    db.session.add(sensor_data)
                    Hardware.query.filter_by(id=sensor_id).one().last_log = dt
                    try:
                        measure_values[measure].append(value)
                    except KeyError:
                        measure_values[measure] = [value]

            for method in summarize:
                for measure in measure_values:
                    values_summarized = round(
                        summarize[method](measure_values[measure]), 2)
                    aggregated_data = sensorData(
                        ecosystem_id=ecosystem_id,
                        sensor_id=method,
                        measure=measure,
                        datetime=dt,
                        value=values_summarized,
                    )
                    db.session.add(aggregated_data)

    db.session.commit()


@sio.on("health_data", namespace="/gaia")
def update_health_data(data):
    manager = engineManager.query.filter_by(sid=request.sid).one()
    sio_logger.debug(f"Received 'update_health_data' from {manager.uid}")
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
    manager = engineManager.query.filter_by(sid=request.sid).one()
    sio_logger.debug(f"Received 'light_data' from {manager.uid}")
    for ecosystem_id in data:
        if data[ecosystem_id].get("lighting_hours"):
            morning_start = time.fromisoformat(
                data[ecosystem_id]["lighting_hours"]["morning_start"])
            morning_end = time.fromisoformat(
                data[ecosystem_id]["lighting_hours"]["morning_end"])
            evening_start = time.fromisoformat(
                data[ecosystem_id]["lighting_hours"]["evening_start"])
            evening_end = time.fromisoformat(
                data[ecosystem_id]["lighting_hours"]["evening_end"])
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
#   SocketIO events coming from browser (non-admin)
# ---------------------------------------------------------------------------
browser_thread = None


# TODO: send sensors data in real time
def browser_background_thread(app):
    with app.app_context():
        global sensorsData
        while True:
            data = {**sensorsData,
                    }
            sio.emit("currentData", "data", namespace="/")
            sio.sleep(3)


@sio.on("connect", namespace="/")
def connect_on_browser():
    global browser_thread
    if browser_thread is None:
        app = current_app._get_current_object()
        browser_thread = sio.start_background_task(
            browser_background_thread, app=app)


@sio.on("my_ping", namespace="/")
def ping_pong():
    incoming_sid = request.sid
    sio.emit("my_pong", namespace="/", room=incoming_sid)


@sio.on("turn_light_on", namespace="/")
def turn_light_on(message):
    ecosystem_id = message["ecosystem"]
    sid = Ecosystem.query.filter_by(id=ecosystem_id).one().manager.sid
    countdown = message.get("countdown", False)
    sio_logger.debug(f"Dispatching 'turn_light_on' signal to ecosystem {ecosystem_id}")
    sio.emit("turn_light_on",
             {"ecosystem": ecosystem_id, "countdown": countdown},
             namespace="/gaia", room=sid)
    return False


@sio.on("turn_light_off", namespace="/")
def turn_light_off(message):
    ecosystem_id = message["ecosystem"]
    sid = Ecosystem.query.filter_by(id=ecosystem_id).one().manager.sid
    countdown = message.get("countdown", False)
    sio_logger.debug(f"Dispatching 'turn_light_off' signal to ecosystem {ecosystem_id}")
    sio.emit("turn_light_off",
             {"ecosystem": ecosystem_id, "countdown": countdown},
             namespace="/gaia", room=sid)
    return False


@sio.on("turn_light_auto", namespace="/")
def turn_light_auto(message):
    ecosystem_id = message["ecosystem"]
    sid = Ecosystem.query.filter_by(id=ecosystem_id).one().manager.sid
    countdown = message.get("countdown", False)
    sio_logger.debug(f"Dispatching 'turn_light_auto' signal to ecosystem {ecosystem_id}")
    sio.emit("turn_light_auto",
             {"ecosystem": ecosystem_id, "countdown": countdown},
             namespace="/gaia", room=sid)
    return False


# ---------------------------------------------------------------------------
#   SocketIO events coming from browser admin
# ---------------------------------------------------------------------------
admin_thread = None


def admin_background_thread(app):
    with app.app_context():
        global sensorsData
        while True:
            data = dict(systemMonitor.system_data)
            # TODO: change JSON parser so it takes datetime data
            del data["datetime"]
            data.update({"uptime": human_delta_time(
                START_TIME, datetime.now(timezone.utc))})
            sio.emit("server_data", data, namespace="/admin")
            sio.sleep(SYSTEM_UPDATE_FREQUENCY)


@sio.on("connect", namespace="/admin")
def connect_on_admin():
    global admin_thread
    if admin_thread is None:
        app = current_app._get_current_object()
        admin_thread = sio.start_background_task(
            admin_background_thread, app=app)
