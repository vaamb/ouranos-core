from socketio import AsyncNamespace

from .events import Events


class GaiaEventsNamespace(AsyncNamespace, Events):
    def __init__(self, namespace: str = None) -> None:
        super().__init__(namespace=namespace)
        self.type = "socketio"
