from __future__ import annotations

from copy import copy
import logging
from logging import Formatter, Handler, LogRecord
import logging.config
from pathlib import Path
import sys
from typing import Literal

import click

from ouranos.core.config.base import BaseConfigDict


TRACE_LOG_LEVEL = 5


class ColourFormatter(Formatter):
    level_colors = {
        TRACE_LOG_LEVEL: lambda level_name: click.style(str(level_name), fg="blue"),
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
            style: Literal["%", "{", "$"] = "%"
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt, style=style)
        self.use_colours = sys.stdout.isatty()

    def color_level_name(self, lvl_name: str, lvl_nbr: int) -> str:
        def default(lvl_name: str) -> str:
            return str(lvl_name)

        func = self.level_colors.get(lvl_nbr, default)
        return func(lvl_name)

    def formatMessage(self, record: LogRecord) -> str:
        record_copy = copy(record)
        lvl_name = record_copy.levelname
        separator = " " * (9 - len(record_copy.levelname))
        if self.use_colours:
            lvl_name = self.color_level_name(lvl_name, record_copy.levelno)
            if "color_message" in record_copy.__dict__:
                record_copy.msg = record_copy.__dict__["color_message"]
                record_copy.__dict__["message"] = record_copy.getMessage()
        record_copy.__dict__["levelname"] = f"{lvl_name}:{separator}"
        return super().formatMessage(record_copy)


handlers: list[str] = []


logging_config = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "base_format": {
            "()": "ouranos.core.logging.ColourFormatter",
            "format": "%(asctime)s %(levelname)s %(name)-30.30s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
    },
    "handlers": {
        "stream_handler": {
            "level": "INFO",
            "formatter": "base_format",
            "class": "logging.StreamHandler",
        },
        "file_handler": {
            "level": "INFO",
            "formatter": "base_format",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "ouranos.log",
            "mode": "a",
            "maxBytes": 4 * 1024 * 1024,
            "backupCount": 5,
        },
    },
    "loggers": {
        "ouranos": {
            "handlers": handlers,
            "level": "INFO"
        },
        "uvicorn": {
            "handlers": handlers,
            "level": "INFO",
        },
    },
}


def configure_logging(config: BaseConfigDict, log_dir: Path) -> None:
    # Prepend log_dir path to the file handler file name
    file_handler_filename = logging_config["handlers"]["file_handler"]["filename"]
    logging_config["handlers"]["file_handler"]["filename"] = str(log_dir / file_handler_filename)

    # Tweak formatters, handlers and loggers if debugging
    if config["DEBUG"]:
        debug_fmt = "%(asctime)s %(levelname)s [%(filename)-20.20s:%(lineno)3d] %(name)-30.30s: %(message)s"
        logging_config["formatters"]["stream_format"]["format"] = debug_fmt
        logging_config["handlers"]["stream_handler"]["level"] = 'DEBUG'
        logging_config["loggers"]["ouranos"]["level"] = 'DEBUG'
        logging_config["loggers"]["uvicorn"]["level"] = 'DEBUG'

    # Use the required handlers
    if config["LOG_TO_STDOUT"]:
        handlers.append("stream_handler")
    if config["LOG_TO_FILE"]:
        handlers.append("file_handler")

    logging.config.dictConfig(logging_config)
