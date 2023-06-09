from __future__ import annotations

from inspect import isclass
import logging.config
from pathlib import Path
import sys
from typing import Type

from ouranos import __version__ as version
from ouranos.core.config.base import BaseConfig, BaseConfigDict
from ouranos.core.config.consts import ImmutableDict
from ouranos.core.utils import stripped_warning


# TODO: find a better alternative as ConfigDict is both a TypedDict and an
#  ImmutableDict. For now: use the TypedDict for type hinting
ConfigDict = BaseConfigDict
profile_type: Type[BaseConfig] | str | None


app_info = {
    "APP_NAME": "Ouranos",
    "VERSION": version,
}


def get_config() -> ConfigDict:
    global _config
    if _config is None:
        stripped_warning(
            "The variable `config` is accessed before setting up config using "
            "`ouranos.setup_config(profile)`. This could lead to unwanted side "
            "effects"
        )
    return _config


def get_base_dir() -> Path:
    global _base_dir
    if _base_dir is None:
        _base_dir = Path(BaseConfig.DIR)
        if not _base_dir.exists():
            raise ValueError(
                "Environment variable `OURANOS_DIR` is not set to a valid path"
            )
    return _base_dir


def _get_dir(name: str, fallback_path: str) -> Path:
    config: ConfigDict = get_config()
    try:
        path = config[name]
        dir_ = Path(path)
    except ValueError:
        stripped_warning(
            f"The dir specified by '{name}' is not valid, using fallback path "
            f"{fallback_path}"
        )
        base_dir = get_base_dir()
        dir_ = base_dir / fallback_path
    if not dir_.exists():
        dir_.mkdir(parents=True)
    return dir_


def get_cache_dir() -> Path:
    return _get_dir("CACHE_DIR", ".cache")


def get_log_dir() -> Path:
    return _get_dir("LOG_DIR", "logs")


def get_db_dir() -> Path:
    return _get_dir("DB_DIR", "DBs")


def _get_config_class(profile: str | None = None) -> Type[BaseConfig]:
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
        cfgs: dict[str | None, Type[BaseConfig]] = {None: BaseConfig}
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
        cfg: Type[BaseConfig] = cfgs.get(profile)
        if cfg:
            return cfg
        else:
            raise RuntimeError(
                f"Could not find config profile {profile} in `config.py`"
            )


def _config_dict_from_class(
        obj: Type[BaseConfig],
        **params,
) -> ConfigDict:
    if not issubclass(obj, BaseConfig):
        raise ValueError("'obj' needs to be a subclass of `BaseConfig`")
    inst = obj()
    config_dict = {}
    for key in dir(inst):
        if not key.isupper():
            continue
        attr = getattr(inst, key)
        if callable(attr):
            config_dict[key] = attr()
        else:
            config_dict[key] = attr
    config_dict.update(params)
    config_dict.update(app_info)
    return ImmutableDict(config_dict)


def configure_logging(config: ConfigDict) -> None:
    debug = config["DEBUG"]
    log_to_stdout = config["LOG_TO_STDOUT"]
    log_to_file = config["LOG_TO_FILE"]
    log_error = config["LOG_ERROR"]

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

    debug_fmt = "%(asctime)s - %(levelname)s [%(filename)-15.15s:%(lineno)4d] %(name)-25.25s: %(message)s"
    regular_fmt = "%(asctime)s - %(levelname)s %(message)s"
    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "streamFormat": {
                "()": "ouranos.core.logging.ColourFormatter",
                "format": f"{debug_fmt if debug else regular_fmt}",
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
            "ouranos": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'INFO'}"
            },
            "dispatcher": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'INFO'}"
            },
            "aiosqlite": {
                "handlers": handlers,
                "level": "WARNING",
            },
            "apscheduler": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
            },
            "urllib3": {
                "handlers": handlers,
                "level": "WARNING",
            },
            "engineio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
            },
            "socketio": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'WARNING'}",
            },
            "uvicorn": {
                "handlers": handlers,
                "level": f"{'DEBUG' if debug else 'INFO'}",
            },
        },
    }
    logging.config.dictConfig(logging_config)


def setup_config(
        profile: profile_type = None,
        **params,
) -> ConfigDict:
    """
    :param profile: name of the config class to use
    :param params: Parameters to override config
    :return: the config as a dict
    """
    global _config
    if _config:
        raise RuntimeError(
            "Trying to setup config a second time"
        )
    if isclass(profile):
        if issubclass(profile, BaseConfig):
            config_cls: Type[BaseConfig] = profile
        else:
            raise ValueError(
                "Class-based profile need to be a subclass of `BaseConfig`"
                )
    else:
        config_cls = _get_config_class(profile)
    config = _config_dict_from_class(config_cls, **params)
    _config = config

    return _config


_config: ConfigDict | None = None
_base_dir: Path | None = None
