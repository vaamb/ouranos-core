from flask import render_template
from flask_login import login_required

from app.models import Permission
from app.admin import bp

@bp.route("api/<echo>")
def echo(echo):
    return echo
