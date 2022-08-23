#!/usr/bin/python3
from setproctitle import setproctitle

import argparse
import logging
import os
import signal
import sys
import uuid

import psutil
import uvicorn

# from dispatcher import configure_dispatcher

from config import config
# from src import services
from src.app import create_app  # , scheduler, sio
from src.utils import configure_logging, humanize_list


config_profiles_available = [profile for profile in config]

default_profile = os.environ.get("OURANOS_PROFILE") or "development"


def get_config(profile):
    if profile.lower() in ("dev", "development"):
        return config["development"]
    elif profile.lower() in ("test", "testing"):
        return config["testing"]
    elif profile.lower() in ("prod", "production"):
        return config["production"]
    else:
        print(f"{profile} is not a valid profile. Valid profiles are "
              f"{humanize_list(config_profiles_available)}.")


parser = argparse.ArgumentParser()

parser.add_argument("-p", "--profile", default=default_profile)


def graceful_exit(logger):
    # services.exit_gracefully()
    logger.info("Ouranos has been closed")
    sys.exit(0)


signal.signal(signal.SIGTERM, graceful_exit)
# rem: signal.SIGINT is translated into KeyboardInterrupt by python


if __name__ == "__main__":
    args = parser.parse_args()
    config_class = get_config(args.profile)
    configure_logging(config_class)
    app_name = config_class.APP_NAME
    logger = logging.getLogger(app_name.lower())

    MAIN = True
    for process in psutil.process_iter():
        if "ouranos" in process.name():
            MAIN = False
            break

    if MAIN:
        setproctitle("ouranos")
    else:
        if not (
            vars(config_class).get("MESSAGE_BROKER_URL") and
            vars(config_class).get("CACHING_SERVER_URL")
        ):
            logger.warning(
                "'MESSAGE_BROKER_URL' and 'CACHING_SERVER_URL' are not defined, "
                "communication between processes won't be allowed, leading to "
                "several issues"
            )
        uid = uuid.uuid4().hex[:8]
        setproctitle(f"ouranos-{uid}")

    try:
        if MAIN:
            # configure_dispatcher(config_class)
            # services.start(config_class)
            pass
        app = create_app(config_class)
        logger.info(f"Starting {app_name} ...")
        uvicorn.run(app, port=5000)
    except KeyboardInterrupt:
        # logger.info("Manually closing gaiaWeb")
        # scheduler.remove_all_jobs()
        # sio.stop()
        graceful_exit(logger)
