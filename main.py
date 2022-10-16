#!/usr/bin/python3
from __future__ import annotations

from setproctitle import setproctitle

setproctitle("ouranos")

import asyncio
import logging

import click
import uvicorn
from uvicorn.loops.auto import auto_loop_setup

import default
from config import default_profile, get_specified_config
from src.core.g import db, scheduler, set_config_globally
from src.core.runner import Runner


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
):
    asyncio.run(
        run(
            config_profile,
            start_api,
            api_workers
        )
    )


async def run(
        config_profile: str,
        start_api: bool,
        api_workers: int,
) -> None:
    # Get the required config
    config = get_specified_config(config_profile)
    # Overwrite config parameters if given in command line
    config["START_API"] = start_api or config.get("START_API", default.START_API)
    config["API_WORKERS"] = api_workers or config.get("API_WORKERS", default.API_WORKERS)
    # Make the config available globally
    set_config_globally(config)
    from src.core.g import config

    # Configure logging
    from src.core.utils import configure_logging, Tokenizer
    configure_logging(config)
    logger: logging.Logger = logging.getLogger(config["APP_NAME"].lower())

    # Configure the Tokenizer
    Tokenizer.secret_key = config["SECRET_KEY"]

    # Init database
    logger.info("Creating database")
    from src.core.database.init import create_base_data
    db.init(config)
    await create_base_data(logger)

    # Init aggregator
    from src.aggregator import Aggregator
    aggregator = Aggregator(config)

    # Init services
    # from src import services

    # Init FastAPI server
    def start_app():
        pass

    def stop_app():
        pass
    if config.get("START_API", default.START_API):
        logger.info("Creating server")
        server_cfg = uvicorn.Config(
            "src.app.factory:create_app", factory=True,
            host="0.0.0.0", port=5000,
            workers=config.get("API_WORKERS", default.API_WORKERS),
            loop="auto",
            server_header=False, date_header=False,
        )
        server = uvicorn.Server(server_cfg)
        if server_cfg.should_reload:
            # TODO: make it work
            from uvicorn.supervisors import ChangeReload
            sock = server_cfg.bind_socket()
            reload = ChangeReload(server_cfg, target=server.run, sockets=[sock])

            def start_app():
                reload.run()

            def stop_app():
                pass
        elif server_cfg.workers > 1:
            # works on linux, not on Windows
            from uvicorn.supervisors import Multiprocess
            sock = server_cfg.bind_socket()
            multi = Multiprocess(server_cfg, target=server.run, sockets=[sock])

            def start_app():
                multi.startup()

            def stop_app():
                multi.shutdown()
        else:
            def start_app():
                asyncio.ensure_future(server.serve())

            def stop_app():
                server.should_exit = True

    # Setup event loop
    use_subprocess: bool = (
        config.get("SERVER_RELOAD", False) or
        (config.get("START_API", default.START_API) and
         config.get("API_WORKERS", default.API_WORKERS) > 1)
    )
    auto_loop_setup(use_subprocess)
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    # Start the app
    runner = Runner()
    scheduler.start()
    aggregator.start()
    # services.start()
    start_app()
    # Override uvicorn signal handlers to also close the scheduler
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.start()
    scheduler.remove_all_jobs()
    aggregator.stop()
    # services.stop()
    stop_app()
    await asyncio.sleep(1.0)


if __name__ == "__main__":
    main()
