from __future__ import annotations

import asyncio
from asyncio import AbstractEventLoop
from concurrent.futures import Future
from copy import copy
import logging
from logging import Formatter, Handler, LogRecord
import logging.config
from pathlib import Path
import sys
from typing import Literal

import click

from ouranos.core.config.base import BaseConfigDict


class DBHandler(Handler):
    def __init__(self) -> None:
        super().__init__()
        self._loop: AbstractEventLoop | None = None
        self._table_created: bool = False

    async def _create_table(self) -> None:
        if self._table_created:
            return

        from ouranos import db
        from ouranos.core.database.models.logging import LogRecord as LogRecordModel  # noqa

        await db.create_all()
        self._table_created = True

    async def _log_record(self, record: LogRecord) -> None:
        from ouranos import db
        from ouranos.core.database.models.logging import LogRecord as LogRecordModel

        if not self._table_created:
            await self._create_table()

        async with db.scoped_session() as session:
            await LogRecordModel.create(session, record)

    def _log_record_error(self, future: Future) -> None:
        exception = future.exception()
        if exception is not None:
            print(f"Failed to log record to the db: {exception}", file=sys.stderr)

    def emit(self, record: LogRecord) -> None:
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                print(f"Failed to log record msg: {record.getMessage()}", file=sys.stderr)
                return
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(self._log_record(record), self._loop)
        future.add_done_callback(self._log_record_error)


class ColourFormatter(Formatter):
    level_colors = {
        logging.DEBUG: lambda lvl_name: click.style(str(lvl_name), fg="cyan"),
        logging.INFO: lambda lvl_name: click.style(str(lvl_name), fg="green"),
        logging.WARNING: lambda lvl_name: click.style(str(lvl_name), fg="yellow"),
        logging.ERROR: lambda lvl_name: click.style(str(lvl_name), fg="red"),
        logging.CRITICAL: lambda lvl_name: click.style(str(lvl_name), fg="bright_red"),
    }

    def __init__(
            self,
            fmt: str | None = None,
            datefmt: str | None = None,
            style: Literal["%", "{", "$"] = "%",
            use_colours: bool | None = None,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.use_colours = sys.stdout.isatty() if use_colours is None else use_colours

    def color_level_name(self, lvl_name: str, lvl_nbr: int) -> str:
        def default(lvl_name: str) -> str:
            return str(lvl_name)

        func = self.level_colors.get(lvl_nbr, default)
        return func(lvl_name)

    def formatMessage(self, record: LogRecord) -> str:
        record_copy = copy(record)
        lvl_name = record_copy.levelname
        separator = " " * (8 - len(record_copy.levelname))
        if self.use_colours:
            lvl_name = self.color_level_name(lvl_name, record_copy.levelno)
            if "color_message" in record_copy.__dict__:
                record_copy.msg = record_copy.__dict__["color_message"]
                record_copy.__dict__["message"] = record_copy.getMessage()
        record_copy.__dict__["levelname"] = f"{lvl_name}:{separator}"
        return super().formatMessage(record_copy)


def configure_logging(config: BaseConfigDict, log_dir: Path) -> None:
    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "base": {
                "()": "ouranos.core.logging.ColourFormatter",
                "format": "%(asctime)s %(levelname)s %(name)-30.30s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "access": {
                "()": "ouranos.core.logging.ColourFormatter",
                "fmt": '%(asctime)s - %(levelname)s %(message)s',
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colours": False,
            },
        },
        "handlers": {
            "stream_handler": {
                "level": "INFO",
                "formatter": "base",
                "class": "logging.StreamHandler",
            },
            "ouranos_file_handler": {
                "level": "INFO",
                "formatter": "base",
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": str(log_dir / "ouranos.log"),
                "when": "W0",
                "backupCount": 4,
            },
            "access_file_handler": {
                "level": "INFO",
                "formatter": "access",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "access.log"),
                "mode": "a",
                "maxBytes": 512 * 1024,
                "backupCount": 4,
            },
            "db_handler": {
                "level": "INFO",
                "class": "ouranos.core.logging.DBHandler",
                "db_path": str(log_dir / "log.sqlite"),
                "table_name": "logs",
            },
        },
        "loggers": {
            "ouranos": {
                "handlers": [],
                "level": "INFO"
            },
            # Plays a role similar to uvicorn.access but for SocketIO events
            "ouranos.web_server.socketio": {
                "handlers": [],
                "level": "INFO",
                "propagate": False,
            },
            "dispatcher": {
                "handlers": [],
                "level": "WARNING",
            },
            # Log everything except "uvicorn.access" into the Ouranos log
            "uvicorn": {
                "handlers": [],
                "level": "INFO",
            },
            # Uvicorn access logs have their own format and go to their own log file
            "uvicorn.access": {
                "handlers": [],
                "level": "INFO",
                "propagate": False,
            },
        },
    }

    # Patch formatters, handlers and loggers if debugging
    if config["DEBUG"]:
        debug_fmt = "%(asctime)s %(levelname)s [%(filename)-20.20s:%(lineno)3d] %(name)-30.30s: %(message)s"
        logging_config["formatters"]["base"]["format"] = debug_fmt
        for handler in logging_config["handlers"].values():
            handler["level"] = "DEBUG"
        for logger in logging_config["loggers"].values():
            logger["level"] = "DEBUG"

    # Patch handlers depending on the config requirements
    if config["LOG_TO_STDOUT"]:
        for logger in logging_config["loggers"].values():
            logger["handlers"].append("stream_handler")

    if config["LOG_TO_FILE"]:
        for logger_name, logger in logging_config["loggers"].items():
            if logger_name in ("ouranos.web_server.socketio", "uvicorn.access"):
                logger["handlers"].append("access_file_handler")
            else:
                logger["handlers"].append("ouranos_file_handler")

    if config["LOG_TO_DB"]:
        for logger in logging_config["loggers"].values():
            logger["handlers"].append("db_handler")

    logging.config.dictConfig(logging_config)
