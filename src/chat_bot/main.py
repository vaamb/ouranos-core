from __future__ import annotations

import asyncio
import logging

import click
from telegram.ext import (
    filters, MessageHandler, ApplicationBuilder, CommandHandler
)

from config import default_profile, get_specified_config
from src.core.g import db, set_config_globally


@click.option(
    "--config-profile",
    type=str,
    default=default_profile,
    help="Configuration profile to use as defined in config.py.",
    show_default=True,
)
def main(
        config_profile: str,
) -> None:
    asyncio.run(
        run(
            config_profile,
        )
    )


async def run(
    config_profile: str | None = None,
) -> None:
    # Check config
    config = get_specified_config(config_profile)
    app_name = config["APP_NAME"].lower()
    from setproctitle import setproctitle
    setproctitle(f"{app_name}-chat_bot")
    set_config_globally(config)
    # Configure logger
    from src.core.g import config
    from src.core.utils import configure_logging
    configure_logging(config)
    logger: logging.Logger = logging.getLogger(config["APP_NAME"].lower())
    # Init database
    logger.info("Initializing database")
    db.init(config)
    from src.core.database.init import create_base_data
    await create_base_data(logger)
    # Start the Chat bot
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    logger.debug("Creating the Aggregator")
    chat_bot = ChatBot(config)
    logger.info("Starting the Aggregator")
    chat_bot.start()
    # Run as long as requested
    from src.core.runner import Runner
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.start()
    chat_bot.stop()


class ChatBot:
    def __init__(
            self,
            config: dict | None = None,
    ):
        from src.core.g import config as global_config
        self.config = config or global_config
        if not self.config:
            raise RuntimeError(
                "Either provide a config dict or set config globally with "
                "g.set_app_config"
            )
        if not self.config.get("TELEGRAM_BOT_TOKEN"):
            raise RuntimeError(
                "The config key 'TELEGRAM_BOT_TOKEN' needs to be set in order "
                "to use the chatbot"
            )
        application = ApplicationBuilder()
        application.token(config["TELEGRAM_BOT_TOKEN"])
        self.application = application.build()

    def load_handlers(self):
        from .commands import ecosystem_status, help_cmd, start, unknown_command
        start_handler = CommandHandler('start', start)
        self.application.add_handler(start_handler)

        ecosystem_status_handler = CommandHandler('ecosystem_status', ecosystem_status)
        self.application.add_handler(ecosystem_status_handler)

        help_handler = CommandHandler("help", help_cmd)
        self.application.add_handler(help_handler)

        unknown_command_handler = MessageHandler(filters.COMMAND, unknown_command)
        self.application.add_handler(unknown_command_handler)

    def start(self):
        self.application.run_polling()

    def stop(self):
        self.application.stop()
