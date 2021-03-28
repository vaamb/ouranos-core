#!/usr/bin/python3
import eventlet

eventlet.monkey_patch()

import logging

from app import create_app, services, scheduler, sio
from app.utils import configure_logging
from config import DevelopmentConfig


config_class = DevelopmentConfig


if __name__ == "__main__":
    try:
        configure_logging(config_class)
        app_name = config_class.APP_NAME
        logger = logging.getLogger(app_name)
        logger.info(f"Starting {app_name} ...")
        services.start()
        app = create_app(config_class)
        logger.info(f"{app_name} successfully started")
        sio.run(app,
                host="0.0.0.0",
                port="5000")
    except KeyboardInterrupt:
        scheduler.remove_all_jobs()
        sio.stop()
        print("Manually closing gaiaWeb")
    finally:
        print("gaiaWeb has been closed")
