from flask import Blueprint
from flask_restx import Api

from .base import namespace as base_ns
from .ecosystems import namespace as ecosystem_ns
from .system import namespace as system_ns
from .weather import namespace as weather_ns


bp = Blueprint("api", __name__, url_prefix="/api")


api = Api(
    bp,
    title="GAIA API",
    version="0.5",
    # description="The API",
)


api.add_namespace(base_ns, path="/app")
api.add_namespace(ecosystem_ns, path="/ecosystems")
api.add_namespace(system_ns, path="/system")
api.add_namespace(weather_ns, path="/weather")
