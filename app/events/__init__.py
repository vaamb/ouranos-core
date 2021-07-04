from dataspace import get_dispatcher

dispatcher = get_dispatcher("Socket.IO")
dispatcher.start()

from app.events import admin, root, gaia
