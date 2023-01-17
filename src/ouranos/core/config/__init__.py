from __future__ import annotations

from inspect import isclass
import logging.config
from pathlib import Path
import sys
from typing import Type

from .base import BaseConfig, DIR
from .consts import ImmutableDict

profile_type: BaseConfig | str | None
config_type: ImmutableDict[str, str | int | bool | dict[str, str]]


app_info = {
    "APP_NAME": "Ouranos",
    "VERSION": "0.5.3",
}


_config: config_type | None = None
_base_dir: Path | None = None


def get_config() -> config_type:
    global _config
    if _config is not None:
        return _config
    raise RuntimeError(
        "You need to setup your configuration using "
        "`ouranos.setup_config(profile)` before accessing config variable"
    )


def get_base_dir() -> Path:
    global _base_dir
    if _base_dir is not None:
        return _base_dir
    raise RuntimeError(
        "You need to setup your configuration using "
        "`ouranos.setup_config(profile)` before accessing base_dir variable"
    )


def _set_base_dir() -> None:
    global _base_dir
    try:
        _base_dir = Path(DIR)
        if not _base_dir.exists():
            raise ValueError
    except ValueError:
        raise RuntimeError(
            "Environment variable `OURANOS_DIR` is not set to a valid path"
        )


def _get_config_class(profile: str | None = None) -> Type:
    _set_base_dir()
    sys.path.extend([str(_base_dir)])
    try:
        import config
    except ImportError:
        if profile is None:
            return BaseConfig
        else:
            raise RuntimeError(
                f"No `config.py` file found and config profile {profile} requested"
            )
    else:
        cfgs: dict[str | None, Type] = {None: BaseConfig}
        for name in dir(config):
            if not name.startswith("__"):
                obj = getattr(config, name)
                if isclass(obj) and issubclass(obj, BaseConfig):
                    if name == "DEFAULT_CONFIG":
                        cfgs[None] = obj
                    else:
                        name = name.lower().strip("config")
                        cfgs[name] = obj
        if profile is not None:
            profile = profile.lower().strip("config")
        cfg: Type = cfgs.get(profile)
        if cfg:
            return cfg
        else:
            raise RuntimeError(
                f"Could not find config profile {profile} in `config.py`"
            )


def _config_dict_from_class(
        obj: Type
) -> config_type:
    return {key: getattr(obj, key) for key in dir(obj) if key.isupper()}


def configure_logging(config: config_type) -> None:
    debug = config.get("DEBUG")
    log_to_stdout = config.get("LOG_TO_STDOUT")
    log_to_file = config.get("LOG_TO_FILE")
    log_error = config.get("LOG_ERROR")

    handlers = []

    if log_to_stdout:
        handlers.append("streamHandler")

    logs_dir_path = config.get("LOG_DIR")
    try:
        logs_dir = Path(logs_dir_path)
    except ValueError:
        print("Invalid logging dir, logging in base dir")
        base_dir = Path(DIR)
        logs_dir = base_dir / ".logs"

    if any((log_to_file, log_error)):
        if not logs_dir.exists():
            logs_dir.mkdir(parents=True)
        if log_to_file:
            handlers.append("fileHandler")
        if log_error:
            handlers.append("errorFileHandler")

    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,

        "formatters": {
            "streamFormat": {
                "format": "%(asctime)s %(levelname)-4.4s [%(filename)-20.20s:%(lineno)3d] %(name)-35.35s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "fileFormat": {
                "format": "%(asctime)s -- %(levelname)s  -- %(name)s -- %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
        },
        "handlers": {
            "streamHandler": {
                "level": f"{'DEBUG' if debug else 'INFO'}",
                "formatter": "streamFormat",
                "class": "logging.StreamHandler",
            },
            "fileHandler": {
                "level": f"{'DEBUG' if debug else 'INFO'}",
                "formatter": "fileFormat",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": f"{logs_dir/'base.log'}",
                "mode": "a",
                "maxBytes": 1024 * 512,
                "backupCount": 5,
            },
            "errorFileHandler": {
                "level": "ERROR",
                "formatter": "fileFormat",
                "class": "logging.FileHandler",
                "filename": f"{logs_dir/'errors.log'}",
                "mode": "a",
            }
        },
        "loggers": {
            "": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'INFO'}"
            },
            "aiosqlite": {
                "handlers": handlers,
                "level": "WARNING",
                "propagate": False,
            },
            "apscheduler": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                "propagate": False,
            },
            "urllib3": {
                "handlers": handlers,
                "level": "WARNING",
                "propagate": False,
            },
            "engineio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                #"propagate": False,
            },
            "socketio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                #"propagate": False,

            },
            "uvicorn": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
                # "propagate": False,
            },
        },
    }
    logging.config.dictConfig(logging_config)


def setup(
        profile: profile_type = None,
        **params,
) -> config_type:
    """
    :param profile: name of the config class to use
    :param params: Parameters to override config
    :return: the config as a dict
    """
    if isclass(profile):
        if issubclass(profile, BaseConfig):
            config_cls: Type = profile
        else:
            raise ValueError(
                "Class-based profile need to be a subclass of `BaseConfig`"
                )
    else:
        config_cls = _get_config_class(profile)
    config = _config_dict_from_class(config_cls)
    config.update(params)
    config.update(app_info)
    configure_logging(config)
    global _config
    _config = ImmutableDict(config)
    return _config
