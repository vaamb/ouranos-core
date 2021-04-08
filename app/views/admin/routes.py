# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone
import secrets

from flask import render_template
from flask_login import login_required
import tracemalloc
from email_validator import validate_email, EmailNotValidError

from app import sio, services, db
from app.views.admin import bp
from app.views.decorators import permission_required
from app.views.main import layout
from app.models import Permission, Service, System, engineManager, User


def system_monitor():
    return services.get_manager().services["system_monitor"]


tracemalloc.start()
s1 = tracemalloc.take_snapshot()
s2 = None
outfile = "mem_leak.debug"


def get_system_data(days=7):
    time_limit = datetime.now(tz=timezone.utc) - timedelta(days=days)
    data = (System.query.filter(System.datetime >= time_limit)
                  .with_entities(System.datetime, 
                                 System.CPU_used, System.CPU_temp,
                                 System.RAM_used, System.RAM_total,
                                 System.DISK_used, System.DISK_total).all())
    return data


def send_invitation(email_address: str,
                    firstname: str = "",
                    lastname: str = "",
                    ) -> dict:
    try:
        email = validate_email(email_address.strip())
    except EmailNotValidError as e:
        return {
            "status": "failed", "info": (email_address, firstname, lastname)
        }

    while True:
        token = secrets.token_hex(16)
        user = User.query.filter(User.token == token)
        if not user:
            break

    user = User(
        email_address=email.email,
        token=token,
        firstname=firstname,
        lastname=lastname,
    )

    # TODO: send actual invitations
    db.session.add(user)
    db.session.commit()
    return {
        "status": "success", "info": (email_address, firstname, lastname, token)
    }


@bp.route('/admin/mem_snapshot')
@login_required
@permission_required(Permission.ADMIN)
def mem_snapshot():
    global s2
    s2 = tracemalloc.take_snapshot()
    diff = []
    with open(outfile, "a+") as file:
        now = datetime.now(tz=timezone.utc)
        file.write(f"{now} \r")
        for i in s2.compare_to(s1,'lineno')[:10]:
            file.write(f"{i} \r")
            diff.append(i)
            file.write("\r")
    return render_template("admin/snapshot.html",
                           diff=diff)


@bp.route("/admin/system")
@login_required
@permission_required(Permission.ADMIN)
def system():
    current_data = system_monitor().system_data
    system_measures = [key for key in current_data if current_data[key]]
    data = get_system_data()
    return render_template("admin/system.html", title="Server monitoring",
                           data=data, current_data=current_data,
                           system_measures=system_measures,
                           parameters=layout.parameters)


@bp.route("/admin/logs")
@login_required
@permission_required(Permission.ADMIN)
def log_home():
    title = "Logs"
    return '''render_template("admin/log_home.html", title=title,
                           )'''


@bp.route("/admin/logs/<log_type>")
@login_required
@permission_required(Permission.ADMIN)
def log(log_type):
    title = "{} logs".format(log_type.capitalize())
    return 'render_template("admin/log.html", title=title)'


@bp.route("/admin/db_management")
@login_required
@permission_required(Permission.ADMIN)
def db_management_home():
    return 'render_template("admin/db_home.html")'


@bp.route("/admin/db_management/<db>")
@login_required
@permission_required(Permission.ADMIN)
def db_management():
    return 'render_template("admin/db_management.html")'


@bp.route("/admin/services")
@login_required
@permission_required(Permission.ADMIN)
def services_management():
    services = Service.query.order_by(Service.name.asc()).all()
    return render_template("admin/services.html", services=services)


@sio.on("manage_service", namespace="/admin")
def start_service(message):
    service = message["service"]
    action = message["action"]
    user = User.query.filter_by(id=message["user_id"]).one()
    if user.is_administrator:
        if action == "start":
            services.get_manager().start_service(service)
            return
        services.get_manager().stop_service(service)


@bp.route("/admin/engine_managers")
@login_required
@permission_required(Permission.OPERATE)
def engine_managers():
    managers = engineManager.query.all()
    return render_template("admin/managers.html", managers=managers)
