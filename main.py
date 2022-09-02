#!/usr/bin/python3
import argparse
import logging
import os
import signal
import sys
import typing as t
import uuid

from fastapi import FastAPI
import psutil
from setproctitle import setproctitle
import uvicorn

# from dispatcher import configure_dispatcher
from config import config_dict, Config, DevelopmentConfig
# from src import services
from src.app import create_app
from src.core.utils import configure_logging, humanize_list


config_profiles_available = [profile for profile in config_dict]

default_profile = os.environ.get("OURANOS_PROFILE") or "development"


def get_config(profile: t.Optional[str]):
    if profile is None or profile.lower() in ("def", "default"):
        return config_dict[default_profile]
    elif profile.lower() in ("dev", "development"):
        return config_dict["development"]
    elif profile.lower() in ("test", "testing"):
        return config_dict["testing"]
    elif profile.lower() in ("prod", "production"):
        return config_dict["production"]
    else:
        raise ValueError(
            f"{profile} is not a valid profile. Valid profiles are "
            f"{humanize_list(config_profiles_available)}."
        )


parser = argparse.ArgumentParser()

parser.add_argument("-p", "--profile", default=default_profile)


def graceful_exit(logger, app_name: str):
    # services.exit_gracefully()
    logger.info(f"{app_name.capitalize()} has been closed")
    sys.exit(0)


signal.signal(signal.SIGTERM, graceful_exit)
# rem: signal.SIGINT is translated into KeyboardInterrupt by python


def create_worker(config_profile: t.Optional[str] = None) -> FastAPI:
    config_profile = config_profile or os.getenv("OURANOS_PROFILE")
    config_class: t.Union[t.Type[Config], t.Type[DevelopmentConfig]]  # TODO: add others
    try:
        config_class = get_config(config_profile)
    except ValueError:
        config_class = get_config("default")
    app_name = config_class.APP_NAME
    main = True
    for process in psutil.process_iter():
        if f"{app_name}-main" in process.name():
            main = False
            break
    if main:
        worker_name = f"{app_name}-main"
        config_class._MAIN = True
    else:
        uid = uuid.uuid4().hex[:8]
        worker_name = f"{app_name}-secondary-{uid}"
        config_class._MAIN = False
    config_class._WORKER_NAME = worker_name
    setproctitle(worker_name.lower())
    logger = logging.getLogger(worker_name.lower())
    logger.info(f"Starting {worker_name} ...")
    if not (
            vars(config_class).get("MESSAGE_BROKER_URL") and
            vars(config_class).get("CACHING_SERVER_URL")
    ):
        logger.warning(
            "'MESSAGE_BROKER_URL' and 'CACHING_SERVER_URL' are not defined, "
            "communication between processes won't be allowed, leading to "
            "several issues"
        )
    # scheduler.start()
    app = create_app(config_class)
    app.extra["main"] = True if main else False
    app.extra["worker_name"] = worker_name
    return app


if __name__ == "__main__":
    args = parser.parse_args()
    config_profile = args.profile
    config = get_config(config_profile)
    configure_logging(config)
    app_name = config.APP_NAME
    logger = logging.getLogger(app_name.lower())
    try:
        uvicorn.run("main:create_worker", port=5000, factory=True, server_header=False)
    except KeyboardInterrupt:
        # scheduler.remove_all_jobs()
        graceful_exit(logger, app_name)
