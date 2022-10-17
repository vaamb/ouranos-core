#!/usr/bin/python3
from __future__ import annotations

import asyncio
import logging

import click

import default
from config import default_profile, get_specified_config
from src.core.g import db, scheduler, set_config_globally


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
    from setproctitle import setproctitle
    setproctitle("ouranos")
    # Get the required config
    config = get_specified_config(config_profile)
    # Overwrite config parameters if given in command line
    config["START_API"] = start_api or config.get("START_API", default.START_API)
    config["API_WORKERS"] = api_workers or config.get("API_WORKERS", default.API_WORKERS)
    # Make the config available globally
    set_config_globally(config)
    from src.core.g import config

    # Configure logger and tokenizer
    from src.core.utils import configure_logging, Tokenizer
    configure_logging(config)
    logger: logging.Logger = logging.getLogger(config["APP_NAME"].lower())
    Tokenizer.secret_key = config["SECRET_KEY"]

    # Init database
    logger.info("Initializing the database")
    from src.core.database.init import create_base_data
    db.init(config)
    await create_base_data(logger)

    # Init app
    from src.app import App
    logger.debug("Creating the App")
    app = App(config)

    # Init aggregator
    from src.aggregator import Aggregator
    logger.debug("Creating the Aggregator")
    aggregator = Aggregator(config)

    # Init services
    # from src import services

    # Start the Monolith
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    logger.debug("Starting the App")
    app.start()
    logger.debug("Starting the Aggregator")
    aggregator.start()
    logger.debug("Starting the Scheduler")
    scheduler.start()

    # Run as long as requested
    from src.core.runner import Runner
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.wait_forever()
    logger.debug("Stopping the Scheduler")
    scheduler.remove_all_jobs()
    logger.debug("Stopping the Aggregator")
    aggregator.stop()
    logger.debug("Stopping the App")
    app.stop()
    await runner.exit()


if __name__ == "__main__":
    main()
