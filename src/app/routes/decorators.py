from functools import wraps

from flask import abort, current_app, request
from flask_login import current_user, config


def permission_required(permission):
    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            if request.method in config.EXEMPT_METHODS:
                return func(*args, **kwargs)
            elif current_app.config.get('LOGIN_DISABLED'):
                return func(*args, **kwargs)
            elif not current_user.can(permission):
                return abort(403)
            return func(*args, **kwargs)
        return decorated_function
    return decorator
