from flask import render_template
from flask_login import login_required

from app.models import Permission
from app.views.api import bp


@bp.route("/api/echo/<echo>")
def echo(echo: str) -> str:
    return echo
