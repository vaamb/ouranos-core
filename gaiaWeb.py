#!/usr/bin/python3
import eventlet

eventlet.monkey_patch()

from app import create_app, scheduler, sio
from config import DevelopmentConfig


app = create_app(DevelopmentConfig)


if __name__ == "__main__":
    try:
        sio.run(app,
                host="0.0.0.0",
                port="5000")
    except KeyboardInterrupt:
        scheduler.remove_all_jobs()
        sio.stop()
        print("Manually closing gaiaWeb")
    finally:
        print("gaiaWeb has been closed")
