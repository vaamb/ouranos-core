from datetime import datetime, time, timezone
import logging
import random

import cachetools
from flask import current_app, request
from flask_login import current_user
from flask_socketio import join_room, leave_room, disconnect
from numpy import mean, std
from sqlalchemy.orm.exc import NoResultFound

from app import app_name, db, scheduler, sio
from dataspace import healthData, sensorsData, sensorsDataHistory
from app.models import sensorData, Ecosystem, engineManager, Hardware, Health, \
    Light, Management, Measure, environmentParameter, Permission
from app.utils import decrypt_uid, validate_uid_token


sio_logger = logging.getLogger(f"{app_name}.socketio")
collector = logging.getLogger(f"{app_name}.collector")

SYSTEM_UPDATE_PERIOD = 5

# Temporary anchors to keep PyCharm to delete these from import
anchor1 = sensorsData

summarize = {"mean": mean, "std": std}


client_blacklist = cachetools.TTLCache(maxsize=62, ttl=60*60*24)


def clear_client_blacklist(client_address: str = None) -> None:
    global client_blacklist
    if not client_address:
        client_blacklist = {}
    else:
        try:
            del client_blacklist[client_address]
        except KeyError:
            pass


# ---------------------------------------------------------------------------
#   Data requests to engineManagers
# ---------------------------------------------------------------------------
gaia_thread = None


# TODO: move into connect_on_gaia
@scheduler.scheduled_job(id="sensors_data", trigger="cron", minute="*",
                         misfire_grace_time=10)
def request_sensors_data(room="engineManagers"):
    if gaia_thread:
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


# TODO: move into connect_on_gaia
@scheduler.scheduled_job(id="light_and_health", trigger="cron",
                         hour="1", misfire_grace_time=15*60)
def request_light_and_health(room="engineManagers"):
    if gaia_thread:
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
    try:
        manager = engineManager.query.filter_by(sid=request.sid).one()
        uid = manager.uid
        leave_room("engineManagers")
        manager.connected = False
        db.session.commit()
        sio.emit(
            "ecosystem_status",
            {ecosystem.id: {"status": ecosystem.status, "connected": False}
             for ecosystem in manager.ecosystem},
            namespace="/"
        )
        sio_logger.info(f"Manager {uid} disconnected")
    except NoResultFound:
        pass


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
    try:
        if client_blacklist[remote_addr] == current_app.config["GAIA_CLIENT_MAX_ATTEMPT"] + 1:
            sio_logger.warning(f"Received three invalid registration requests "
                               f"from {remote_addr}.")

        if client_blacklist[remote_addr] > current_app.config["GAIA_CLIENT_MAX_ATTEMPT"]:
            over_attempts = client_blacklist[remote_addr] - 2
            if over_attempts > 4:
                over_attempts = 4
            fix_tempering = 1.5 ** over_attempts  # max 5 secs
            if fix_tempering > 5:
                fix_tempering = 5
            random_tempering = 2 * random.random() - 1  # [-1: 1]
            sio.sleep(fix_tempering + random_tempering)
            disconnect()
            return False
    except KeyError:
        # Not in blacklist
        pass
    manager_uid = decrypt_uid(data["ikys"])

    if not validate_uid_token(data["uid_token"], manager_uid):
        try:
            client_blacklist[remote_addr] += 1
        except KeyError:
            client_blacklist[remote_addr] = 1
        sio_logger.info(f"Received invalid registration request from {remote_addr}")
        disconnect()
    else:
        try:
            del client_blacklist[remote_addr]
        except KeyError:
            pass
        now = datetime.now(timezone.utc).replace(microsecond=0)
        manager = engineManager(
            uid=manager_uid,
            sid=request.sid,
            connected=True,
            registration_date=now,
            last_seen=now,
            address=f"{remote_addr}:{remote_port}",
        )

        db.session.merge(manager)
        db.session.commit()
        join_room("engineManagers")

        sio.emit("register_ack", namespace="/gaia", room=request.sid)
        sio_logger.info(f"Successful registration of manager {manager_uid}, "
                        f"from {remote_addr}:{remote_port}")
        request_config(request.sid)
        request_sensors_data(request.sid)
        request_light_data(request.sid)
        request_health_data(request.sid)


# TODO: transform into a wrap?
def check_manager_identity(event):
    manager = engineManager.query.filter_by(sid=request.sid).first()
    if not manager:
        remote_addr = request.environ["REMOTE_ADDR"]
        remote_port = request.environ["REMOTE_PORT"]
        sio_logger.warning(f"Received '{event}' event on '/gaia' from unknown "
                           f"client with address {remote_addr}:{remote_port}")
        sio.emit("register", namespace="/gaia", room=request.sid)
        return False
    return manager


@sio.on("engines_change", namespace="/gaia")
def reload_all():
    manager = check_manager_identity("config")
    if manager:
        request_config(request.sid)
        request_sensors_data(request.sid)
        request_light_data(request.sid)
        request_health_data(request.sid)


@sio.on("config", namespace="/gaia")
def update_cfg(config):
    manager = check_manager_identity("config")
    if manager:
        for ecosystem_id in config:
            try:
                day_start = datetime.strptime(
                    config[ecosystem_id]["environment"]["day"]["start"], "%Hh%M"
                ).time()
                night_start = datetime.strptime(
                    config[ecosystem_id]["environment"]["night"]["start"],
                    "%Hh%M"
                ).time()
            except KeyError:
                day_start = night_start = None
            ecosystem = Ecosystem(
                id=ecosystem_id,
                name=config[ecosystem_id]["name"],
                status=config[ecosystem_id]["status"],
                manager_uid=manager.uid,
                day_start=day_start,
                night_start=night_start,
            )

            for m in Management:
                try:
                    if config[ecosystem_id]["management"][m]:
                        ecosystem.add_management(Management[m])
                except KeyError:
                    # Not implemented yet
                    pass
            db.session.merge(ecosystem)

            for parameter in ("temperature", "humidity", "light"):
                for moment_of_day in ("day", "night"):
                    try:
                        environment_parameter = environmentParameter(
                            ecosystem_id=ecosystem_id,
                            parameter=parameter,
                            moment_of_day=moment_of_day,
                            value=(config[ecosystem_id]["environment"]
                                         [moment_of_day][parameter]),
                            hysteresis=(config[ecosystem_id]["environment"]
                                              ["hysteresis"][parameter]),
                        )
                        db.session.merge(environment_parameter)
                    except KeyError:
                        pass

            # TODO: first delete all hardware from this ecosystem present there before, so if delete in config, deleted here too
            for hardware_uid in config[ecosystem_id].get("IO", {}):
                hardware = Hardware(
                    id=hardware_uid,
                    ecosystem_id=ecosystem_id,
                    name=config[ecosystem_id]["IO"][hardware_uid]["name"],
                    address=config[ecosystem_id]["IO"][hardware_uid]["address"],
                    type=config[ecosystem_id]["IO"][hardware_uid]["type"],
                    level=config[ecosystem_id]["IO"][hardware_uid]["level"],
                    model=config[ecosystem_id]["IO"][hardware_uid]["model"],
                )

                measures = config[ecosystem_id]["IO"][hardware_uid].get(
                        "measure", [])
                if isinstance(measures, str):
                    measures = [measures]
                for measure in measures:
                    _measure = Measure(
                        name=measure
                    )

                    hardware.measure.append(_measure)
                db.session.merge(hardware)
        sio.emit(
            "ecosystem_status",
            {ecosystem.id: {"status": ecosystem.status, "connected": True}
             for ecosystem in manager.ecosystem},
            namespace="/"
        )
        db.session.commit()

# TODO: split this in two part: one receiving and logging data, and move the one sending data to a scheduled event
@sio.on("sensors_data", namespace="/gaia")
def update_sensors_data(data):
    manager = check_manager_identity("config")
    if manager:
        sio_logger.debug(f"Received 'sensors_data' from manager: {manager.uid}")
        sensorsData.update(data)

        sio.emit("current_sensors_data", data, namespace="/")

        for ecosystem_id in data:
            try:
                dt = datetime.fromisoformat(data[ecosystem_id]["datetime"])
            # When launching, gaiaEngine is sometimes still loading its sensors
            except KeyError:
                continue
            sensorsData[ecosystem_id]["datetime"] = dt
            if dt.minute % current_app.config["SENSORS_LOGGING_PERIOD"] == 0:
                # Delete cached data for sensors.html page
                try:
                    del sensorsDataHistory[ecosystem_id]
                except KeyError:
                    pass
                measure_values = {}
                # TODO: add ecosystem name
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
                        # There can only be 1
                        db.session.merge(sensor_data)
                        Hardware.query.filter_by(id=sensor_id).one().last_log = dt

                        try:
                            measure_values[measure].append(value)
                        except KeyError:
                            measure_values[measure] = [value]

                for method in summarize:
                    for measure in measure_values:
                        # Set a minimum threshold before summarizing values
                        if len(measure_values[measure]) >= 3:
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
    manager = check_manager_identity("config")
    if manager:
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
    manager = check_manager_identity("config")

    def try_fromiso(isotime):
        try:
            return time.fromisoformat(isotime)
        except TypeError:
            return None

    if manager:
        sio_logger.debug(f"Received 'light_data' from {manager.uid}")
        for ecosystem_id in data:
            if data[ecosystem_id].get("lighting_hours"):
                morning_start = try_fromiso(
                    data[ecosystem_id]["lighting_hours"].get("morning_start"))
                morning_end = try_fromiso(
                    data[ecosystem_id]["lighting_hours"].get("morning_end"))
                evening_start = try_fromiso(
                    data[ecosystem_id]["lighting_hours"].get("evening_start"))
                evening_end = try_fromiso(
                    data[ecosystem_id]["lighting_hours"].get("evening_end"))
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
        sio.emit("light_data", data, namespace="/")


# ---------------------------------------------------------------------------
#   SocketIO events coming from browser (non-admin)
# ---------------------------------------------------------------------------
@sio.on("connect", namespace="/")
def connect_on_browser():
    if any((current_app.config["DEBUG"], current_app.config["TESTING"])):
        remote_addr = request.environ["REMOTE_ADDR"]
        remote_port = request.environ["REMOTE_PORT"]
        sio_logger.debug(f"Connection from {remote_addr}:{remote_port}")


@sio.on("disconnect", namespace="/")
def connect_on_browser():
    if any((current_app.config["DEBUG"], current_app.config["TESTING"])):
        remote_addr = request.environ["REMOTE_ADDR"]
        remote_port = request.environ["REMOTE_PORT"]
        sio_logger.debug(f"Disconnection of {remote_addr}:{remote_port}")


@sio.on("my_ping", namespace="/")
def ping_pong():
    incoming_sid = request.sid
    sio.emit("my_pong", namespace="/", room=incoming_sid)


@sio.on("turn_light", namespace="/")
def turn_light(message):
    if not current_user.can(Permission.OPERATE):
        return False
    ecosystem_id = message["ecosystem"]
    sid = Ecosystem.query.filter_by(id=ecosystem_id).one().manager.sid
    mode = message.get("mode", "automatic")
    countdown = message.get("countdown", False)
    sio_logger.debug(
        f"Dispatching 'turn_light_{mode}' signal to ecosystem {ecosystem_id}")
    sio.emit("turn_light",
             {"ecosystem": ecosystem_id, "mode": mode, "countdown": countdown},
             namespace="/gaia", room=sid)
    return False


# ---------------------------------------------------------------------------
#   SocketIO events coming from browser admin
# ---------------------------------------------------------------------------
admin_thread = None


def admin_background_thread(app):
    return True
    with app.app_context():
        pass


@sio.on("connect", namespace="/admin")
def connect_on_admin():
    # Close connection if request not from an authenticated admin
    if not current_user.can(Permission.ADMIN):
        disconnect()
    global admin_thread
    if admin_thread is None:
        app = current_app._get_current_object()
        admin_thread = sio.start_background_task(
            admin_background_thread, app=app)
