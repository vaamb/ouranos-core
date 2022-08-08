from flask_restx import Namespace

namespace = Namespace(
    "gaia",
    description="Information about the registered ecosystems.",
)

from . import ecosystem, hardware, engine
