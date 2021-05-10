#!/usr/bin/python3
from setproctitle import setproctitle

setproctitle("gaiaWeb")

import eventlet

eventlet.monkey_patch()

import logging
import sys

from app import create_app, dataspace, services, scheduler, sio
from app.utils import configure_logging, humanize_list
from config import DevelopmentConfig, TestingConfig, ProductionConfig


config_profile = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig
}
profiles_available = [profile for profile in config_profile]

default_profile = "development"


if __name__ == "__main__":
    try:
        profile = default_profile
        if len(sys.argv) > 1:
            profile = sys.argv[1]
        try:
            config_class = config_profile[profile]
        except KeyError:
            raise ValueError(f"Profile {profile} not available, Please choose "
                             f"from {humanize_list(profiles_available)}")

        configure_logging(config_class)
        app_name = config_class.APP_NAME
        logger = logging.getLogger(app_name)
        logger.info(f"Starting {app_name} ...")
        dataspace.init(config_class)
        services.start(config_class)
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
        # TODO: set managers as not connected on closing
        #  engineManager.query.update({engineManager.connected: False})
        print("gaiaWeb has been closed")
