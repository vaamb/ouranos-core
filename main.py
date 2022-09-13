#!/usr/bin/python3
import argparse
import asyncio
import logging
import signal
import sys

import uvicorn

# from src import services
from src.core.g import db, scheduler, set_config, set_base_dir
from src.core.utils import (
    configure_logging, config_dict_from_class, default_profile, get_config_class,
    Tokenizer
)


try:
    import uvloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


parser = argparse.ArgumentParser()

parser.add_argument("-p", "--profile", default=default_profile)


async def create_base_data():
    from src.core.database.models import (
        CommunicationChannel, Measure, Role, User
    )
    await db.create_all()
    async with db.scoped_session() as session:
        try:
            await CommunicationChannel.insert_channels(session)
            await Measure.insert_measures(session)
            await Role.insert_roles(session)
            await User.insert_gaia(session)
        except Exception as e:
            logger.error(e)
            raise e


def graceful_exit(logger, app_name: str):
    # services.exit_gracefully()
    logger.info(f"{app_name.capitalize()} has been closed")
    sys.exit(0)


signal.signal(signal.SIGTERM, graceful_exit)
# rem: signal.SIGINT is translated into KeyboardInterrupt by python


if __name__ == "__main__":
    args = parser.parse_args()
    config_profile = args.profile
    config_cls = get_config_class(config_profile)
    config = config_dict_from_class(config_cls)
    configure_logging(config)
    # Make the chosen config available globally
    set_config(config)
    if config.get("DIR"):
        set_base_dir(config["DIR"])
    app_name = config["APP_NAME"]
    logger = logging.getLogger(app_name.lower())
    Tokenizer.secret_key = config["SECRET_KEY"]
    loop = asyncio.get_event_loop()
    try:
        logger.info("Creating database")
        db.init(config)
        loop.run_until_complete(create_base_data())
        if config.get("SERVER", True):
            logger.info("Creating server")
            server_cfg = uvicorn.Config(
                "app:create_app", factory=True,
                port=5000,
                workers=config.get("WORKERS", 1),
                loop=loop if not config.get("WORKERS", 1) > 1 else "auto",
                server_header=False, date_header=False,
            )
            server = uvicorn.Server(server_cfg)
            if server_cfg.should_reload:
                # TODO: make it work
                from uvicorn.supervisors import ChangeReload
                sock = server_cfg.bind_socket()
                reload = ChangeReload(server_cfg, target=server.run, sockets=[sock])
                reload.run()
            elif server_cfg.workers > 1:
                # works on linux, not on Windows
                from uvicorn.supervisors import Multiprocess
                sock = server_cfg.bind_socket()
                multi = Multiprocess(server_cfg, target=server.run, sockets=[sock])
                multi.startup()
            else:
                loop.create_task(server.serve())
        else:
            from src.aggregator import create_aggregator
            aggregator = create_aggregator(config)
            aggregator.start(loop)
        scheduler._eventloop = loop
        scheduler.start()
        loop.run_forever()
    except KeyboardInterrupt:
        scheduler.remove_all_jobs()
        loop.stop()
        graceful_exit(logger, app_name)
