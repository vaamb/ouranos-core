from src.dataspace import get_dispatcher

dispatcher = get_dispatcher("application")
dispatcher.start()

from src.app.events import admin, root, gaia
