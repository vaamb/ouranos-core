from dispatcher import AsyncEventHandler

from .events import Events


class GaiaEventsNamespace(AsyncEventHandler, Events):
    def __init__(self, namespace: str = None):
        super().__init__(namespace=namespace)
