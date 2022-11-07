from __future__ import annotations

import asyncio
import logging

import click
from telegram.ext import (
    filters, MessageHandler, ApplicationBuilder, CommandHandler
)

from ouranos import db, setup_config


@click.command()
@click.option(
    "--config-profile",
    type=str,
    default=None,
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
    from setproctitle import setproctitle
    setproctitle("ouranos-chat_bot")
    # Setup config
    config = setup_config(config_profile)
    logger: logging.Logger = logging.getLogger("ouranos.chat_bot")
    # Init database
    logger.info("Initializing database")
    db.init(config)
    from ouranos.core.database.init import create_base_data
    await create_base_data(logger)
    # Start the Chat bot
    loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    logger.debug("Creating the Chat bot")
    chat_bot = ChatBot(config)
    logger.info("Starting the Chat bot")
    chat_bot.start()
    # Run as long as requested
    from ouranos.sdk.runner import Runner
    runner = Runner()
    await asyncio.sleep(0.1)
    runner.add_signal_handler(loop)
    await runner.wait_forever()
    chat_bot.stop()
    await runner.exit()


class ChatBot:
    def __init__(
            self,
            config: dict | None = None,
    ):
        from ouranos import current_app
        self.config = config or current_app.config
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
        self.load_handlers()

    def load_handlers(self):
        from src.chat_bot.commands import (
            ecosystem_status, help_cmd, start, unknown_command
        )
        start_handler = CommandHandler('start', start)
        self.application.add_handler(start_handler)

        ecosystem_status_handler = CommandHandler('ecosystem_status', ecosystem_status)
        self.application.add_handler(ecosystem_status_handler)

        help_handler = CommandHandler("help", help_cmd)
        self.application.add_handler(help_handler)

        unknown_command_handler = MessageHandler(filters.COMMAND, unknown_command)
        self.application.add_handler(unknown_command_handler)

    def start(self):
        async def _start():
            await self.application.initialize()
            await self.application.updater.start_polling()
            await self.application.start()

        loop = asyncio.get_event_loop()
        loop.create_task(_start())

    def stop(self):
        async def _stop():
            if self.application.updater.running:
                await self.application.updater.stop()
            if self.application.running:
                await self.application.stop()
            await self.application.shutdown()

        loop = asyncio.get_event_loop()
        loop.create_task(_stop())
