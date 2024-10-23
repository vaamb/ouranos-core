from __future__ import annotations

from inspect import isclass
import logging
import os
import sys
from typing import Type

from anyio import Path

from ouranos import __version__ as version
from ouranos.core.config.base import BaseConfig, BaseConfigDict
from ouranos.core.config.consts import ImmutableDict
from ouranos.core.logging import configure_logging


# TODO: find a better alternative as ConfigDict is both a TypedDict and an
#  ImmutableDict. For now: use the TypedDict for type hinting
ConfigDict = BaseConfigDict
profile_type: Type[BaseConfig] | str | None


app_info = {
    "APP_NAME": "Ouranos",
    "VERSION": version,
}


class ConfigHelper:
    _config: ConfigDict | None = None

    @classmethod
    def _get_config_class(cls, profile: str | None = None) -> Type[BaseConfig]:
        logger = logging.getLogger("ouranos.config_helper")
        lookup_dir = os.environ.get("OURANOS_DIR")
        if lookup_dir is not None:
            logger.info("Trying to get Ouranos config from 'OURANOS_DIR'.")
        else:
            logger.info("Trying to get Ouranos config from current directory.")
            lookup_dir = os.getcwd()

        sys.path.insert(0, str(lookup_dir))

        try:
            import config
        except ImportError:
            if profile is None:
                return BaseConfig
            else:
                raise ValueError(
                    f"No `config.py` file found and config profile {profile} requested"
                )
        else:
            cfgs: dict[str | None, Type[BaseConfig]] = {None: BaseConfig}
            for name in dir(config):
                if not name.startswith("__"):
                    obj = getattr(config, name)
                    if (
                            isclass(obj) and issubclass(obj, BaseConfig)
                            and obj is not BaseConfig
                    ):
                        if name == "DEFAULT_CONFIG":
                            cfgs[None] = obj
                        else:
                            name = name.lower().replace("config", "")
                            cfgs[name] = obj
            if profile is not None:
                profile = profile.lower().replace("config", "")
            cfg: Type[BaseConfig] = cfgs.get(profile)
            if cfg:
                return cfg
            else:
                raise ValueError(
                    f"Could not find config profile {profile} in `config.py`"
                )

    @classmethod
    def _config_dict_from_class(
            cls,
            config_cls: Type[BaseConfig],
            **params,
    ) -> ConfigDict:
        if not issubclass(config_cls, BaseConfig):
            raise ValueError("'obj' needs to be a subclass of `BaseConfig`")
        config_inst = config_cls()
        config_dict = {}
        for key in dir(config_inst):
            if not key.isupper():
                continue
            attr = getattr(config_inst, key)
            if callable(attr):
                config_dict[key] = attr()
            else:
                config_dict[key] = attr
        config_dict.update(params)
        config_dict.update(app_info)
        return ImmutableDict(config_dict)

    @classmethod
    def config_is_set(cls) -> None:
        return cls._config is not None

    @classmethod
    def get_config(cls) -> ConfigDict:
        if cls._config is None:
            raise RuntimeError(
                "The variable `config` is accessed before setting up config using "
                "`ouranos.setup_config(profile)`. This could lead to unwanted side "
                "effects"
            )
        return cls._config

    @classmethod
    def set_config(
            cls,
            profile: profile_type = None,
            **params,
    ) -> ConfigDict:
        """
        :param profile: name of the config class to use
        :param params: Parameters to override config
        :return: the config as a dict
        """
        if cls._config is not None:
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
            config_cls = cls._get_config_class(profile)
        cls._config = cls._config_dict_from_class(config_cls, **params)
        return cls._config

    @classmethod
    def set_config_and_configure_logging(
            cls,
            profile: profile_type = None,
            **params,
    ) -> ConfigDict:
        config = cls.set_config(profile, **params)
        configure_logging(config=config, log_dir=get_log_dir())
        return config

    @classmethod
    def reset_config(cls) -> None:
        if not cls.config_is_set():
            raise ValueError("Cannot reset a non-set config.")
        if not cls._config.get("TESTING"):
            raise ValueError("Only testing config can be reset.")
        cls._config = None


setup_config = ConfigHelper.set_config
get_config = ConfigHelper.get_config


class PathsHelper:
    _dirs: dict[str, Path] = {}

    @classmethod
    def _get_dir(cls, dir_name: str) -> Path:
        try:
            return cls._dirs[dir_name]
        except KeyError:
            try:
                config = ConfigHelper.get_config()
                path = Path(config[dir_name])
            except ValueError:
                raise ValueError(f"Config.{dir_name} is not a valid directory.")
            else:
                if not await path.exists():
                    logger = logging.getLogger("ouranos.paths_helper")
                    logger.warning(
                        f"'Config.{dir_name}' variable is set to a non-existing "
                        f"directory, trying to create it.")
                    await path.mkdir(parents=True)
                cls._dirs[dir_name] = path
                return path

    @classmethod
    def get_base_dir(cls) -> Path:
        return cls._get_dir("DIR")

    @classmethod
    def get_cache_dir(cls) -> Path:
        return cls._get_dir("CACHE_DIR")

    @classmethod
    def get_log_dir(cls) -> Path:
        return cls._get_dir("LOG_DIR")

    @classmethod
    def get_db_dir(cls) -> Path:
        return cls._get_dir("DB_DIR")

    @classmethod
    def get_static_dir(cls) -> Path:
        return cls._get_dir("STATIC_DIR")


get_base_dir = PathsHelper.get_base_dir
get_cache_dir = PathsHelper.get_cache_dir
get_log_dir = PathsHelper.get_log_dir
get_db_dir = PathsHelper.get_db_dir
get_static_dir = PathsHelper.get_static_dir
