# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

from flask import render_template
from flask_login import login_required
import tracemalloc

from app import sio
from app.views.admin import bp
from app.views.common.decorators import permission_required
from app.dataspace import systemMonitor
from app.main import layout
from app.models import Permission, Service, System, engineManager, User
from app.services import services_manager


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
    system_data = systemMonitor.system_data
    system_measures = list(system_data.keys())
    data = get_system_data()
    return render_template("admin/system.html", title="Server monitoring",
                           data=data, system_data=system_data,
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
    services = Service.query.all()
    return render_template("admin/services.html", services=services)


@sio.on("manage_service", namespace="/browser")
def start_service(message):
    service = message["service"]
    action = message["action"]
    user = User.query.filter_by(id=message["user_id"]).one()
    if user.is_administrator:
        if action == "start":
            services_manager.start(service)
            return
        services_manager.stop(service)


@bp.route("/admin/engine_managers")
@login_required
@permission_required(Permission.OPERATE)
def engine_managers():
    managers = engineManager.query.all()
    return render_template("admin/managers.html", managers=managers)
