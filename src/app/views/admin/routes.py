from datetime import datetime, timedelta, timezone

from flask import current_app, render_template, redirect, url_for, flash
import tracemalloc

from src.app import db, API
from src.app.views import layout
from src.app.views.admin import bp
from src.app.views.admin.forms import InvitationForm
from src.app.models import Service


"""Remark:
All the routes here are protected and require user to be logged in and 
administrator
"""


tracemalloc.start()
s1 = tracemalloc.take_snapshot()
s2 = None
outfile = "mem_leak.debug"


@bp.route("/invite", methods=["GET", "POST"])
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
            API.admin.send_invitation(invitation_jwt=invitation_jwt,
                                      db_session=db.session)
            flash(f"Invitation email sent to {form.email.data}")
        elif form.invitation_channel.data == "telegram":
            # TODO: send invitation
            flash(f"Invitation message sent to telegram user {form.telegram_chat_id.data}")
        return redirect(url_for("admin.invite_user"))

    return render_template("admin/invite_user.html", title="Invite new user",
                           form=form)


@bp.route('/mem_snapshot')
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


@bp.route("/system")
def system():
    current_system_data = API.admin.get_current_system_data()
    system_measures = [key for key in current_system_data
                       if current_system_data[key]]
    graphUpdatePeriod = current_app.config["SYSTEM_LOGGING_PERIOD"]
    return render_template("admin/system.html", title="Server monitoring",
                           graphUpdatePeriod=graphUpdatePeriod,
                           system_measures=system_measures,
                           parameters=layout.parameters)


@bp.route("/logs")
@bp.route("/logs/<level>")
def logs(level: str = "base"):
    if level != "error":
        level = "base"
    title = "{} logs".format(level.capitalize())
    logs = API.admin.get_logs(level=level)
    return render_template("admin/logs.html", title=title, logs=logs)


@bp.route("/db_management")
def db_management_home():
    return 'render_template("admin/db_home.html")'


@bp.route("/db_management/<db>")
def db_management(db):
    return 'render_template("admin/db_management.html")'


@bp.route("/services")
def services_management():
    # TODO: move to API
    services_available = [
        service.to_dict() for service in
        Service.query.order_by(Service.name.asc()).all()
    ]
    return render_template("admin/services.html", services=services_available)
