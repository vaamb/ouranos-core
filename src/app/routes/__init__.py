from flask import Blueprint
from flask_restx import Api

from .api_doc import authorizations


bp = Blueprint("api", __name__, url_prefix="/api")

api = Api(
    bp,
    title="Ouranos API",
    version="0.5",
    description="Backend Ouranos API",
    doc='/doc',
    authorizations=authorizations,
)


from . import error_handlers
from .app import namespace as app_ns
from .auth import namespace as auth_ns
from .gaia import namespace as gaia_ns
from .system import namespace as system_ns
from .weather import namespace as weather_ns


api.add_namespace(app_ns, path="/app")
api.add_namespace(auth_ns, path="/auth")
api.add_namespace(gaia_ns, path="/gaia")
api.add_namespace(system_ns, path="/system")
api.add_namespace(weather_ns, path="/weather")
