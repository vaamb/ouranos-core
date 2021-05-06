# -*- coding: utf-8 -*-
from datetime import datetime, timedelta, timezone

from flask import render_template, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy.orm.exc import NoResultFound
import tracemalloc

from app import sio, services, db, API
from app.views.admin import bp
from app.views.admin.forms import InvitationForm
from app.views.decorators import permission_required
from app.views.main import layout
from app.models import Permission, Service, System, engineManager, User


def system_monitor():
    return services.get_manager().services["system_monitor"]


tracemalloc.start()
s1 = tracemalloc.take_snapshot()
s2 = None
outfile = "mem_leak.debug"


@bp.route("/admin/invite", methods=["GET", "POST"])
@login_required
@permission_required(Permission.ADMIN)
def invite_user():
    form = InvitationForm()
    form.expiration.data = 7

    if form.validate_on_submit():
        invitation_jwt = API.admin.create_invitation_jwt(
            db_session=db.session,
            first_name=form.firstname.data,
            last_name=form.lastname.data,
            email_address=form.email.data,
            telegram_chat_id=form.telegram_chat_id.data,
            role=form.role.data,
            expiration_delay=timedelta(days=form.expiration.data),
        )

        if form.invitation_channel.data == "link":
            flash(
                "Here is the invitation token:\r\n"
                f"{invitation_jwt}",
                # TODO: auto copy to clipboard
                category="display"
            )
        elif form.invitation_channel.data == "email":
            API.admin.send_invitation(invitation_jwt=invitation_jwt)
            flash(f"Invitation email sent to {form.email.data}")
        elif form.invitation_channel.data == "telegram":
            # TODO: send invitation
            flash(f"Invitation message sent to telegram user {form.telegram_chat_id.data}")
        return redirect(url_for("admin.invite_user"))

    return render_template("admin/invite_user.html", title="Invite new user",
                           form=form)


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
    data = API.admin.get_system_data(db.session)
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
    services_available = Service.query.order_by(Service.name.asc()).all()
    return render_template("admin/services.html", services=services_available)


@sio.on("manage_service", namespace="/admin")
def start_service(message):
    service = message["service"]
    action = message["action"]
    try:
        user = User.query.filter_by(id=message["user_id"]).one()
    except NoResultFound:
        return
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
