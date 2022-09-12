#!/usr/bin/python3
import argparse
import asyncio
import logging
import signal
import sys

from setproctitle import setproctitle
import uvicorn

# from src import services
from src.app import create_app, dispatcher as app_dispatcher
from src.core.g import scheduler
from src.core.utils import (
    configure_logging, config_dict_from_class, default_profile, get_config
)


try:
    import uvloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


parser = argparse.ArgumentParser()

parser.add_argument("-p", "--profile", default=default_profile)


def graceful_exit(logger, app_name: str):
    # services.exit_gracefully()
    logger.info(f"{app_name.capitalize()} has been closed")
    sys.exit(0)


signal.signal(signal.SIGTERM, graceful_exit)
# rem: signal.SIGINT is translated into KeyboardInterrupt by python


if __name__ == "__main__":
    args = parser.parse_args()
    config_profile = args.profile
    config_cls = get_config(config_profile)
    configure_logging(config_cls)
    config = config_dict_from_class(config_cls)
    app_name = config["APP_NAME"]
    logger = logging.getLogger(app_name.lower())
    try:
        app = create_app(config_profile)
        loop = asyncio.get_event_loop()
        scheduler._eventloop = loop
        workers = config.get("WORKERS", 1)
        if workers == 1:
            cfg = uvicorn.Config(
                app,
                port=5000,
                workers=config.get("WORKERS", 1),
                loop=loop,
                server_header=False, date_header=False,
            )
            server = uvicorn.Server(cfg)
            loop.create_task(server.serve())
        else:
            raise NotImplementedError(
                "It is currently impossible to use more than one worker"
            )
        app_dispatcher.start()
        scheduler.start()
        loop.run_forever()
    except KeyboardInterrupt:
        app_dispatcher.stop()
        scheduler.remove_all_jobs()
        graceful_exit(logger, app_name)
