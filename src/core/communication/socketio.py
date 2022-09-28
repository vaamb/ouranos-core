from socketio import AsyncNamespace

from .events import Events


class GaiaEventsNamespace(AsyncNamespace, Events):
    type = "socketio"

    def __init__(self, namespace: str = None):
        super().__init__(namespace=namespace)
