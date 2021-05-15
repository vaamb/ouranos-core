#!/usr/bin/python3
from setproctitle import setproctitle

setproctitle("gaiaWeb")

import eventlet

eventlet.monkey_patch()

import argparse
import logging
import signal
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


def get_config(profile):
    if profile.lower() in ("dev", "development"):
        return config_profile["development"]
    elif profile.lower() in ("test", "testing"):
        return config_profile["testing"]
    elif profile.lower() in ("prod", "production"):
        return config_profile["production"]
    else:
        print(f"{profile} is not a valid profile. Valid profiles are "
              f"{humanize_list(profiles_available)}.")


parser = argparse.ArgumentParser()

parser.add_argument("-p", "--profile", default=default_profile)


def graceful_exit(*args):
    services.exit_gracefully()
    print("gaiaWeb has been closed")
    sys.exit(0)


signal.signal(signal.SIGTERM, graceful_exit)
# rem: signal.SIGINT is translated into KeyboardInterrupt by python


if __name__ == "__main__":
    try:
        args = parser.parse_args()
        config_class = get_config(args.profile)
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
        print("Manually closing gaiaWeb")
    finally:
        sio.stop()
        graceful_exit()
