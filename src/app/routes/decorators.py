from functools import wraps

from flask import abort, request, current_app
from flask_login import current_user, config as fl_config


# Same as flask login but return 403
def login_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if request.method in fl_config.EXEMPT_METHODS:
            return func(*args, **kwargs)
        elif current_app.config.get('LOGIN_DISABLED'):
            return func(*args, **kwargs)
        elif not current_user.is_authenticated:
            return abort(401)
        return func(*args, **kwargs)
    return decorated_view
