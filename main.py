#!/usr/bin/python3
from __future__ import annotations

import asyncio
import logging
import signal
from types import FrameType

import click
import uvicorn
from uvicorn.loops.auto import auto_loop_setup

import default
from config import default_profile, get_specified_config
from src.core.g import db, scheduler, set_config_globally, set_base_dir


should_exit = False


def stop():
    global should_exit
    should_exit = True


def handle_signal(sig: int, frame: FrameType | None):
    stop()


async def runner():
    global should_exit
    while not should_exit:
        await asyncio.sleep(0.2)


SIGNALS = (
    signal.SIGINT,
    signal.SIGTERM,
)


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
    config["SERVER"] = start_api or config.get("SERVER", default.FASTAPI)
    config["WORKERS"] = api_workers or config.get("WORKERS", default.WORKERS)
    # Make the config available globally
    set_config_globally(config)
    from src.core.g import config
    # Change base dir if required
    if config.get("DIR"):
        set_base_dir(config["DIR"])

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
    from src.aggregator import create_aggregator
    aggregator = create_aggregator(config)

    # Init services
    # from src import services

    # Init FastAPI server
    def start_app():
        pass

    def stop_app():
        pass
    if config.get("SERVER", default.FASTAPI):
        logger.info("Creating server")
        server_cfg = uvicorn.Config(
            "src.app:create_app", factory=True,
            port=5000,
            workers=config.get("WORKERS", default.WORKERS),
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
        (config.get("SERVER", default.FASTAPI) and
         config.get("WORKERS", default.WORKERS) > 1)
    )
    auto_loop_setup(use_subprocess)
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    # Start the app
    scheduler.start()
    aggregator.start()
    # services.start()
    start_app()
    # Override uvicorn signal handlers to also close the scheduler
    await asyncio.sleep(0.1)
    try:
        for sig in SIGNALS:
            loop.add_signal_handler(sig, handle_signal, sig, None)
    except NotImplementedError:
        for sig in SIGNALS:
            signal.signal(sig, handle_signal)
    await runner()
    scheduler.remove_all_jobs()
    aggregator.stop()
    # services.stop()
    stop_app()
    await asyncio.sleep(1.0)


if __name__ == "__main__":
    main()
