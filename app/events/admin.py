from flask import current_app
from flask_login import current_user
from flask_socketio import disconnect
from sqlalchemy.orm.exc import NoResultFound

from app import sio
import dataspace
from app.models import Permission, User


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
            order = {"target": "start_service", "args": (service, )}
        else:
            order = {"target": "stop_service", "args": (service,)}
        dataspace.app_to_services_queue.put(order)
