from datetime import datetime, date
import pytz
from json import JSONEncoder
import psutil

from flask import current_app, request
from flask_socketio import emit #, join_room, leave_room will be needed to notify the correct user, depending on env he is working on

from app import socketio
from app.main import aggregates
from app.main.filters import human_delta_time


class DateTimeEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()


"""Background global events""" 
thread = None

def background_thread(app):
    with app.app_context():
        while True:
            socketio.sleep(1)
            aggregates.update_resources_data()
            try:
                temp = psutil.sensors_temperatures()
                CPU_temp = temp["cpu-thermal"][0][1]
            except AttributeError: #if machine is not raspi
                CPU_temp = None
            socketio.emit(
                "data",
                {"CPU_used": aggregates.resources_data["CPU"],
                 "CPU_temp": CPU_temp,
                 "RAM_used": aggregates.resources_data["RAM_used"],
                 "DISK_used": aggregates.resources_data["DISK_used"],
                 "uptime": human_delta_time(aggregates.start_time,
                                            datetime.now().astimezone(pytz.timezone(aggregates.timezone))),
                 "sensors_data": DateTimeEncoder().encode(aggregates.sensors_data)
                 },
                 namespace="/test")

@socketio.on("connect", namespace="/test")
def background_task():
    global thread
    if thread is None:
        app = current_app._get_current_object()
        thread = socketio.start_background_task(background_thread, app=app)

@socketio.on('disconnect', namespace="/test")
def on_disconnect():
    #print ("Client disconnected...", request.sid)
    pass

@socketio.on("my_ping", namespace="/test")
def ping_pong():
    emit("my_pong")

"""Light events"""
@socketio.on("light_on", namespace="/test")
def turn_light_on(message):
    ecosystem = message["ecosystem"]
    aggregates.engines[ecosystem].set_light_on()
    return False

@socketio.on("light_off", namespace="/test")
def turn_light_off(message):
    ecosystem = message["ecosystem"]
    aggregates.engines[ecosystem].set_light_off()
    return False

@socketio.on("light_auto", namespace="/test")
def turn_light_auto(message):
    ecosystem = message["ecosystem"]
    aggregates.engines[ecosystem].set_light_auto()
    return False