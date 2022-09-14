#!/usr/bin/python3
from __future__ import annotations

import asyncio
import logging
import signal
from types import FrameType

import click
import uvicorn

from config import default_profile, get_specified_config
# from src import services
from src.core.g import db, scheduler, set_config_globally, set_base_dir
from src.core.utils import configure_logging, Tokenizer


try:
    import uvloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


loop = asyncio.get_event_loop()
stop_event = asyncio.Event()


def handle_signal(sig: int, frame: FrameType | None):
    loop.stop()


SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
)

for SIG in SIGNALS:
    signal.signal(SIG, handle_signal)


DEFAULT_FASTAPI = True
DEFAULT_WORKERS = 1


@click.command(context_settings={"auto_envvar_prefix": "OURANOS"})
@click.option(
    "--config-profile",
    type=str,
    default=default_profile,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
@click.option(
    "--start-api",
    type=bool,
    is_flag=True,
    default=None,
    help="Start FastAPI server.",
    show_default=True,
)
@click.option(
    "--api-workers",
    type=int,
    default=None,
    help="Number of FastAPI workers to start using uvicorn",
    show_default=True,
)
def main(
        config_profile: str,
        start_api: bool,
        api_workers: int,
) -> None:
    config = get_specified_config(config_profile)
    config["SERVER"] = start_api or config.get("SERVER", DEFAULT_FASTAPI)
    config["WORKERS"] = api_workers or config.get("WORKERS", DEFAULT_WORKERS)
    set_config_globally(config)
    from src.core.g import config
    configure_logging(config)
    # Make the chosen config available globally
    if config.get("DIR"):
        set_base_dir(config["DIR"])
    app_name = config["APP_NAME"]
    logger = logging.getLogger(app_name.lower())
    Tokenizer.secret_key = config["SECRET_KEY"]
    logger.info("Creating database")
    from src.core.database.init import create_base_data
    db.init(config)
    loop.run_until_complete(create_base_data(logger))
    if config.get("SERVER", True):
        logger.info("Creating server")
        server_cfg = uvicorn.Config(
            "app:create_app", factory=True,
            port=5000,
            workers=config.get("WORKERS", 1),
            loop="auto",
            server_header=False, date_header=False,
        )
        server = uvicorn.Server(server_cfg)
        if server_cfg.should_reload:
            # TODO: make it work
            from uvicorn.supervisors import ChangeReload
            sock = server_cfg.bind_socket()
            reload = ChangeReload(server_cfg, target=server.run, sockets=[sock])
            reload.run()

            def stop_app():
                pass
        elif server_cfg.workers > 1:
            # works on linux, not on Windows
            from uvicorn.supervisors import Multiprocess
            sock = server_cfg.bind_socket()
            multi = Multiprocess(server_cfg, target=server.run, sockets=[sock])
            multi.startup()

            def stop_app():
                multi.shutdown()
        else:
            loop.create_task(server.serve())

            def stop_app():
                server.should_exit = True
    else:
        from src.aggregator import create_aggregator
        aggregator = create_aggregator(config)
        aggregator.start(loop)

        def stop_app():
            aggregator.stop()
    scheduler._eventloop = loop
    scheduler.start()
    loop.run_forever()
    stop_app()
    scheduler.remove_all_jobs()
    scheduler.stop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        signal.raise_signal(signal.SIGINT)
