#!/usr/bin/python3
from __future__ import annotations

import asyncio
import logging

import click

from ouranos import db, scheduler, setup_config


@click.command(context_settings={"auto_envvar_prefix": "OURANOS"})
@click.option(
    "--config-profile",
    type=str,
    default=None,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
def main(
        config_profile: str | None,
):
    asyncio.run(
        run(
            config_profile,
        )
    )


async def run(
        config_profile: str | None = None,
) -> None:
    from setproctitle import setproctitle
    setproctitle("ouranos")
    # Setup config
    config = setup_config(config_profile)
    logger: logging.Logger = logging.getLogger("ouranos")
    # Init database
    logger.info("Initializing the database")
    from ouranos.core.database.init import create_base_data
    db.init(config)
    await create_base_data(logger)

    # Init web_server
    from ouranos.web_server import WebServer
    logger.debug("Creating the Web server")
    web_server = WebServer(config)

    # Init aggregator
    from ouranos.aggregator import Aggregator
    logger.debug("Creating the Aggregator")
    aggregator = Aggregator(config)

    # Init services
    # from ouranos import services
    # Start the Monolith
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    logger.debug("Starting the Web server")
    web_server.start()
    logger.debug("Starting the Aggregator")
    aggregator.start()
    logger.debug("Starting the Scheduler")
    scheduler.start()

    """
    from ouranos.core.plugin import PluginManager
    plugin_manager = PluginManager()
    plugin_manager.register_plugins()
    """
    # Run as long as requested
    from ouranos.sdk.runner import Runner
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.wait_forever()
    logger.debug("Stopping the Scheduler")
    scheduler.remove_all_jobs()
    logger.debug("Stopping the Aggregator")
    aggregator.stop()
    logger.debug("Stopping the Api")
    web_server.stop()
    await runner.exit()


if __name__ == "__main__":
    main()
