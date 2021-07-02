from werkzeug.local import LocalProxy

from app import sio
from dataspace import services_to_app_queue, STOP_SIGNAL


_thread = None


def dispatch_events():
    while True:
        message = services_to_app_queue.get()
        if message == STOP_SIGNAL:
            services_to_app_queue.task_done()
            break
        event = message["event"]
        kwargs = {}
        for k in ("data", "namespace", "room"):
            load = message.get(k)
            if load:
                if isinstance(load, LocalProxy):
                    load = {**load}  # Need to unpack and repack for LocalProxy
                kwargs.update({k: load})
        sio.emit(event=event, **kwargs)
        services_to_app_queue.task_done()


def start():
    global _thread
    if not _thread:
        _thread = sio.start_background_task(dispatch_events)


def stop():
    services_to_app_queue.put(STOP_SIGNAL)
    services_to_app_queue.join()
    global _thread
    _thread = None
