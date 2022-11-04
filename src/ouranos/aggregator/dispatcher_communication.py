from dispatcher import AsyncEventHandler

from ouranos.aggregator.events import Events


class GaiaEventsNamespace(AsyncEventHandler, Events):
    type = "dispatcher"

    def __init__(self, namespace: str = None) -> None:
        super().__init__(namespace=namespace)
