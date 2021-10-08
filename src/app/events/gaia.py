from datetime import datetime, time, timezone
import logging
import random

import cachetools
from flask import current_app, request
from flask_socketio import disconnect, join_room, leave_room
from numpy import mean, std
from sqlalchemy.exc import IntegrityError, NoResultFound

from src.app import app_name, db, scheduler, sio
from src.app.events import dispatcher
from src.models import Ecosystem, EngineManager, EnvironmentParameter, \
    Hardware, HealthData, Light, Management, Measure, SensorData
from src.app.utils import decrypt_uid, validate_uid_token
from src.dataspace import healthData, sensorsData


# TODO: change name
sio_logger = logging.getLogger(f"{app_name}.socketio")
# TODO: better use
collector = logging.getLogger(f"{app_name}.collector")


_thread = None


summarize = {"mean": mean, "std": std}


managers_blacklist = cachetools.TTLCache(maxsize=62, ttl=60 * 60 * 24)


def clear_client_blacklist(client_address: str = None) -> None:
    global managers_blacklist
    if not client_address:
        managers_blacklist = cachetools.TTLCache(maxsize=62, ttl=60 * 60 * 24)
    else:
        try:
            del managers_blacklist[client_address]
        except KeyError:
            pass


# ---------------------------------------------------------------------------
#   Data requests to engineManagers
# ---------------------------------------------------------------------------
# TODO: move into connect_on_gaia
@scheduler.scheduled_job(id="sensors_data", trigger="cron", minute="*",
                         misfire_grace_time=10)
def request_sensors_data(room="engineManagers"):
    if _thread:
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
    if _thread:
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
    global _thread
    if _thread is None:
        _thread = []
        app = current_app._get_current_object()
        _thread.append(sio.start_background_task(
            gaia_background_thread, app=app))


@sio.on("disconnect", namespace="/gaia")
def disconnect():
    try:
        manager = EngineManager.query.filter_by(sid=request.sid).one()
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
def pong(data):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    manager = EngineManager.query.filter_by(sid=request.sid).one()
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
        if managers_blacklist[remote_addr] == current_app.config["GAIA_CLIENT_MAX_ATTEMPT"] + 1:
            sio_logger.warning(f"Received three invalid registration requests "
                               f"from {remote_addr}.")

        if managers_blacklist[remote_addr] > current_app.config["GAIA_CLIENT_MAX_ATTEMPT"]:
            over_attempts = managers_blacklist[remote_addr] - 2
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
            managers_blacklist[remote_addr] += 1
        except KeyError:
            managers_blacklist[remote_addr] = 1
        sio_logger.info(f"Received invalid registration request from {remote_addr}")
        disconnect()
    else:
        try:
            del managers_blacklist[remote_addr]
        except KeyError:
            pass
        now = datetime.now(timezone.utc).replace(microsecond=0)
        # TODO: check if manager not already connected
        manager = EngineManager(
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
def check_manager_identity(event) -> EngineManager:
    manager = EngineManager.query.filter_by(sid=request.sid).first()
    if not manager:
        remote_addr = request.environ["REMOTE_ADDR"]
        remote_port = request.environ["REMOTE_PORT"]
        sio_logger.warning(f"Received '{event}' event on '/gaia' from unknown "
                           f"client with address {remote_addr}:{remote_port}")
        sio.emit("register", namespace="/gaia", room=request.sid)
        # TODO: raise error?
        return EngineManager()
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
            try:
                environment_parameter = (
                    db.session.query(EnvironmentParameter)
                              .filter_by(ecosystem_id=ecosystem_id)
                              .filter_by(parameter=parameter)
                              .one_or_none()
                )
                if not environment_parameter:
                    environment_parameter = EnvironmentParameter(
                        ecosystem_id=ecosystem_id,
                        parameter=parameter,
                    )
                environment_parameter.day = (config[ecosystem_id]
                    ["environment"]["day"][parameter])
                environment_parameter.night = (config[ecosystem_id]
                    ["environment"]["night"][parameter])
                environment_parameter.hysteresis = (config[ecosystem_id]
                    ["environment"]["hysteresis"][parameter])
                db.session.add(environment_parameter)
            except KeyError:
                pass

        # TODO: first delete all hardware from this ecosystem present there
        #  before, so if delete in config, deleted here too
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
        [{"uid": ecosystem.id, "status": ecosystem.status, "connected": True}
         for ecosystem in manager.ecosystem],
        namespace="/"
    )
    db.session.commit()


# TODO: split this in two part: one receiving and logging data, and move the
#  one sending data to a scheduled event
@sio.on("sensors_data", namespace="/gaia")
def update_sensors_data(data):
    manager = check_manager_identity("config")
    if manager:
        sio_logger.debug(f"Received 'sensors_data' from manager: {manager.uid}")
        dispatcher.emit("application", "sensors_data", data=data)
        # TODO: add a room specific for each ecosystem?
        sio.emit("current_sensors_data", data, namespace="/")
        for ecosystem in data:
            try:
                dt = datetime.fromisoformat(ecosystem["datetime"])
            # When launching, gaiaEngine is sometimes still loading its sensors
            except KeyError:
                continue

            if dt.minute % current_app.config["SENSORS_LOGGING_PERIOD"] == 0:
                measure_values = {}
                collector.debug(f"Logging sensors data from ecosystem: {ecosystem['ecosystem_uid']}")

                for sensor in ecosystem["data"]:
                    sensor_uid = sensor["sensor_uid"]
                    for measure in sensor["measures"]:
                        value = float(measure["values"])
                        sensor_data = SensorData(
                            ecosystem_id=ecosystem["ecosystem_uid"],
                            sensor_id=sensor_uid,
                            measure=measure["name"],
                            datetime=dt,
                            value=value,
                        )

                        try:
                            db.session.add(sensor_data)
                            Hardware.query.filter_by(
                                id=sensor_uid).one().last_log = dt
                        except IntegrityError:
                            collector.warning(
                                f"Already have a {measure['name']} data point at {dt} "
                                f"for {sensor_uid}"
                            )

                        try:
                            measure_values[measure["name"]].append(value)
                        except KeyError:
                            measure_values[measure["name"]] = [value]

                for method in summarize:
                    for measure in measure_values:
                        # Set a minimum threshold before summarizing values
                        # TODO: add the option to summarize or not
                        if len(measure_values[measure]) >= 3:
                            values_summarized = round(
                                summarize[method](measure_values[measure]), 2)
                            aggregated_data = SensorData(
                                ecosystem_id=ecosystem["ecosystem_uid"],
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
        dispatcher.emit("application", "health_data", data=data)
        # healthData.update(data)
        for d in data:
            health = HealthData(
                ecosystem_id=d["ecosystem_uid"],
                datetime=datetime.fromisoformat(d["datetime"]),
                green=d["green"],
                necrosis=d["necrosis"],
                health_index=d["health_index"]
            )
            db.session.add(health)
        db.session.commit()


@sio.on("light_data", namespace="/gaia")
def update_light_data(data):
    # TODO: log status 
    manager = check_manager_identity("config")

    def try_from_iso(isotime):
        try:
            return time.fromisoformat(isotime)
        except TypeError:
            return None

    if manager:
        sio_logger.debug(f"Received 'light_data' from {manager.uid}")
        for d in data:
            morning_start = try_from_iso(d.get("morning_start", None))
            morning_end = try_from_iso(d.get("morning_end", None))
            evening_start = try_from_iso(d.get("evening_start", None))
            evening_end = try_from_iso(d.get("evening_end", None))
            light = Light(
                ecosystem_id=d["ecosystem_uid"],
                status=d["status"],
                mode=d["mode"],
                method=d["method"],
                morning_start=morning_start,
                morning_end=morning_end,
                evening_start=evening_start,
                evening_end=evening_end
            )
            db.session.merge(light)
        db.session.commit()
        sio.emit("light_data", data, namespace="/")


# ---------------------------------------------------------------------------
#   Dispatcher events
# ---------------------------------------------------------------------------
@dispatcher.on("turn_light")
def _turn_light(*args, **kwargs):
    sio.emit("turn_light", namespace="/gaia", **kwargs)


@dispatcher.on("turn_actuator")
def _turn_actuator(*args, **kwargs):
    sio.emit("turn_actuator", namespace="/gaia", **kwargs)


@dispatcher.on("sensors_data")
def update_sensors_data(data):
    sensorsData.update(
        {ecosystem["ecosystem_uid"]: ecosystem for ecosystem in data}
    )
