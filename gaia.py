#!/usr/bin/python
import eventlet

eventlet.monkey_patch()

from app import create_app, scheduler, sio


app = create_app()


if __name__ == "__main__":
    try:
        sio.run(app,
                host="0.0.0.0",
                port="5000")
    except KeyboardInterrupt:
        scheduler.remove_all_jobs()
        print("Manually closing gaiaWeb")
    finally:
        print("gaiaWeb has been closed")
