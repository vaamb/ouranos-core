from flask import abort, Blueprint, current_app
from flask_login import current_user

from src.models import Permission


bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def restrict_to_admins():
    if not current_app.config.get("LOGIN_DISABLED") and \
            not current_user.is_authenticated:
        return current_app.login_manager.unauthorized()
    if not current_user.can(Permission.ADMIN):
        abort(403, "{}".format(Permission.ADMIN))


from src.app.views.admin import routes

