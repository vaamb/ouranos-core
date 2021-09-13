from src.dataspace import get_dispatcher

dispatcher = get_dispatcher("Socket.IO")
dispatcher.start()

from src.app.events import admin, root, gaia
