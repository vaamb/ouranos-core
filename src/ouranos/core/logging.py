from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import copy
import logging
from logging import Formatter, Handler, LogRecord
import logging.config
from pathlib import Path
import sqlite3
import sys
import time
from typing import Literal

import click

from ouranos.core.config.base import BaseConfigDict


class SQLiteHandler(Handler):
    _create_query = """\
    CREATE TABLE IF NOT EXISTS %(table_name)s(
        timestamp TEXT,
        level_name TEXT,
        level INT,
        logger_name TEXT,
        file_name TEXT,
        line_no INT,
        func_name TEXT,
        message TEXT
    )"""

    _log_query = """\
    INSERT INTO %(table_name)s(
        timestamp,
        level_name,
        level,
        logger_name,
        file_name,
        line_no,
        func_name,
        message
   )
   VALUES (
        '%(timestamp)s',
        %(levelno)d,
        '%(levelname)s',
        '%(name)s',
        '%(filename)s',
        %(lineno)d,
        '%(funcName)s',
        '%(msg)s'
   );
    """

    def __init__(self, db_path: Path, table_name: str) -> None:
        super().__init__()
        parent_dir = Path(db_path).parent
        if not parent_dir.exists():
            parent_dir.mkdir(parents=True)
        self.db_path = db_path
        self.table_name = table_name
        self._table_created: bool = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='db_logging')

    def _execute_query(self, query: str) -> None:
        db = sqlite3.connect(self.db_path)
        db.execute(query)
        db.commit()

    def execute_query(self, query: str) -> None:
        self._executor.submit(self._execute_query, query)

    def create_table(self) -> None:
        query = self._create_query % {"table_name": self.table_name}
        self.execute_query(query)

    def log_record(self, record: LogRecord) -> None:
        query = self._log_query % {"table_name": self.table_name, **record.__dict__}
        self.execute_query(query)

    def format_time(self, record: LogRecord) -> None:
        record.timestamp = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created))

    def emit(self, record: LogRecord) -> None:
        if not self._table_created:
            self.create_table()
            self._table_created = True
        self.format_time(record)
        self.log_record(record)


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
            "db_handler": {
                "level": "INFO",
                "class": "ouranos.core.logging.SQLiteHandler",
                "db_path": "log.sqlite",
                "table_name": "logs",
            },
        },
        "loggers": {
            "ouranos": {
                "handlers": [],
                "level": "INFO"
            },
            "dispatcher": {
                "handlers": [],
                "level": "WARNING",
            },
            "uvicorn": {
                "handlers": [],
                "level": "INFO",
            },
        },
    }

    def make_file_handler(filename: str, size: int = 4 * 1024 * 1024, count: int = 5) -> dict:
        return {
            "level": "INFO",
            "formatter": "base_format",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": filename,
            "mode": "a",
            "maxBytes": size,
            "backupCount": count,
        }

    # Add file handlers
    logging_config["handlers"]["ouranos_file_handler"] = make_file_handler("ouranos.log", count=2)
    logging_config["handlers"]["uvicorn_file_handler"] = make_file_handler("uvicorn.log", count=5)

    # Prepend log_dir path to the file handler file name
    for handler in logging_config["handlers"].values():
        if handler["class"] == "logging.handlers.RotatingFileHandler":
            handler["filename"] = str(log_dir / handler["filename"])

    # Prepend log_dir path to the file handler file name
    for handler in logging_config["handlers"].values():
        if handler["class"] == "logging.handlers.SQLiteHandler":
            handler["db_path"] = str(log_dir / handler["db_path"])

    # Patch formatters, handlers and loggers if debugging
    if config["DEBUG"]:
        debug_fmt = "%(asctime)s %(levelname)s [%(filename)-20.20s:%(lineno)3d] %(name)-30.30s: %(message)s"
        logging_config["formatters"]["base_format"]["format"] = debug_fmt
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
            if logger_name == "uvicorn":
                logger["handlers"].append("uvicorn_file_handler")
            else:
                logger["handlers"].append("ouranos_file_handler")

    if config["LOG_TO_DB"]:
        for logger in logging_config["loggers"].values():
            logger["handlers"].append("db_handler")

    logging.config.dictConfig(logging_config)
