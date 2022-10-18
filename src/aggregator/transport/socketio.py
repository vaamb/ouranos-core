from socketio import AsyncNamespace

from src.aggregator.events import Events


class GaiaEventsNamespace(AsyncNamespace, Events):
    type = "socketio"

    def __init__(self, namespace: str = None) -> None:
        super().__init__(namespace=namespace)
