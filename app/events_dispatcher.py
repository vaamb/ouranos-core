
from app import sio
from dataspace import sio_queue


_thread = None


def dispatch_events():
    while True:
        message = sio_queue.get()
        if message == "STOP":
            sio_queue.task_done()
            break
        event = message["event"]
        data = message["data"]
        namespace = message.get("namespace", "/")
        sio.emit(event=event, data=data, namespace=namespace)
        sio_queue.task_done()


def start():
    global _thread
    if not _thread:
        _thread = sio.start_background_task(dispatch_events)


def stop():
    sio_queue.put("STOP")
    sio_queue.join()
    global _thread
    _thread = None
