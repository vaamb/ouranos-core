from dispatcher import AsyncEventHandler

from .events import Events


class GaiaEventsNamespace(AsyncEventHandler, Events):
    pass
