from __future__ import annotations

from inspect import isclass
import logging.config
from pathlib import Path
import sys
from typing import Type

from .base import BaseConfig, DIR
from .consts import ImmutableDict
from ouranos.core.utils import stripped_warning

profile_type: BaseConfig | str | None
config_type: ImmutableDict[str, str | int | bool | dict[str, str]]


app_info = {
    "APP_NAME": "Ouranos",
    "VERSION": "0.5.3",
}


def get_config() -> config_type:
    global _config
    if not _config["SET_UP"]:
        stripped_warning(
            "The variable `config` is accessed before setting up config using "
            "`ouranos.setup_config(profile)`. This could lead to unwanted side "
            "effects"
        )
    return _config


def get_base_dir() -> Path:
    global _base_dir
    if _base_dir is None:
        _base_dir = Path(DIR)
        if not _base_dir.exists():
            raise ValueError(
                "Environment variable `OURANOS_DIR` is not set to a valid path"
            )
    return _base_dir


def _get_dir(name: str, fallback_path: str) -> Path:
    config: config_type = get_config()
    path = config.get(name)
    try:
        dir_ = Path(path)
    except ValueError:
        # TODO: use warnings and log that we are not using the given path
        base_dir = get_base_dir()
        dir_ = base_dir / fallback_path
    if not dir_.exists():
        dir_.mkdir(parents=True)
    return dir_


def get_cache_dir() -> Path:
    return _get_dir("CACHE_DIR", ".cache")


def get_log_dir() -> Path:
    return _get_dir("LOG_DIR", ".logs")


def _get_config_class(profile: str | None = None) -> Type:
    base_dir = get_base_dir()
    sys.path.extend([str(base_dir)])
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
        obj: Type,
        set_up: bool = True,
        **params,
) -> config_type:
    config_dict = {key: getattr(obj, key) for key in dir(obj) if key.isupper()}
    config_dict.update({"SET_UP": set_up})
    config_dict.update(params)
    config_dict.update(app_info)
    return ImmutableDict(config_dict)


def configure_logging(config: config_type) -> None:
    debug = config.get("DEBUG")
    log_to_stdout = config.get("LOG_TO_STDOUT")
    log_to_file = config.get("LOG_TO_FILE")
    log_error = config.get("LOG_ERROR")

    handlers = []

    if log_to_stdout:
        handlers.append("streamHandler")

    log_dir = get_base_dir()
    if log_to_file or log_error:
        if log_to_file:
            handlers.append("fileHandler")
        if log_error:
            handlers.append("errorFileHandler")
        log_dir = get_log_dir()

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
                "filename": f"{log_dir / 'base.log'}",
                "mode": "a",
                "maxBytes": 1024 * 512,
                "backupCount": 5,
            },
            "errorFileHandler": {
                "level": "ERROR",
                "formatter": "fileFormat",
                "class": "logging.FileHandler",
                "filename": f"{log_dir / 'errors.log'}",
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
    config = _config_dict_from_class(config_cls, **params)
    global _config
    _config = config
    configure_logging(config)

    return _config


_config: config_type = _config_dict_from_class(BaseConfig, False)
_base_dir: Path | None = None
