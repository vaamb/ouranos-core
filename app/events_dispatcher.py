from app import sio
from dataspace import services_to_app_queue


_thread = None


def dispatch_events():
    while True:
        message = services_to_app_queue.get()
        if message == "STOP":
            services_to_app_queue.task_done()
            break
        event = message["event"]
        data = message["data"]
        namespace = message.get("namespace", "/")
        sio.emit(event=event, data={**data}, namespace=namespace)
        services_to_app_queue.task_done()


def start():
    global _thread
    if not _thread:
        _thread = sio.start_background_task(dispatch_events)


def stop():
    services_to_app_queue.put("STOP")
    services_to_app_queue.join()
    global _thread
    _thread = None
