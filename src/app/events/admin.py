from flask import current_app
from flask_login import current_user
from flask_socketio import disconnect
from sqlalchemy.orm.exc import NoResultFound

from src.app import sio
from src.app.events import dispatcher
from src.app.models import Permission, User
from src.dataspace import systemData


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


@sio.on("manage_service", namespace="/admin")
def start_service(message):
    service = message["service"]
    action = message["action"]
    try:
        user = User.query.filter_by(id=message["user_id"]).one()
    except NoResultFound:
        return
    if user.can(Permission.ADMIN):
        if action == "start":
            dispatcher.emit("services", "start_service", service)
        else:
            dispatcher.emit("services", "stop_service", service)


@dispatcher.on("current_server_data")
def current_server_data(data):
    systemData.update(data)
    sio.emit(event="current_server_data", data=data, namespace="/admin")
