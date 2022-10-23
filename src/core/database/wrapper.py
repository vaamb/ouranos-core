# Recipe adapted from https://flask.palletsprojects.com/en/1.1.x/patterns/sqlalchemy/
# and heavily inspired by Flask_SQLAlchemy.
# The recipe has been wrapped inside a class to be more convenient.
# If working inside app context, DO NOT use this!


from __future__ import annotations

from asyncio import current_task
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Coroutine, Generator, AsyncGenerator
import warnings

from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.engine import create_engine, Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession, AsyncEngine, create_async_engine, async_scoped_session
)
from sqlalchemy.orm import scoped_session, Session, sessionmaker

from src.core.database._base import base


@dataclass
class Config:
    uri: str
    binds: dict[str, str]


class SQLAlchemyWrapper:
    """Convenience wrapper to use SQLAlchemy

    For a safe use, use as follows:
    ``
    db = SQLAlchemyWrapper()
    with db.scoped_session() as session:
        session.your_query_here
    ``
    This will automatically create a scoped session and remove it at the end of
    the scope.
    """
    _Model: DeclarativeMeta = base

    def __init__(
            self,
            config: type | str | dict | None = None,
            model=_Model,
    ):
        self.Model: DeclarativeMeta = model
        self._session_factory: sessionmaker | None = None
        self._session: scoped_session | None = None
        self._engines: dict[str | None, Engine] = {}
        self._config: Config | None = None

        if config:
            self.init(config)

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        return self._session()

    @property
    def config(self) -> Config:
        if self._config is None:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        return self._config

    def init(self, config_object: type | str | dict) -> None:
        self._init_config(config_object)
        self._create_session_factory()

    def _init_config(self, config_object: type | str | dict) -> None:
        if isinstance(config_object, type):
            from config import config_dict_from_class
            config = config_dict_from_class(config_object)
        elif isinstance(config_object, str):
            config = {"SQLALCHEMY_DATABASE_URI": config_object}
        elif isinstance(config_object, dict):
            config = config_object
        else:
            raise TypeError("config_object can either be a str, a dict or a class")
        if "SQLALCHEMY_DATABASE_URI" not in config:
            raise RuntimeError(
                "Config object needs the parameter 'SQLALCHEMY_DATABASE_URI'"
            )
        self._config = Config(
            uri=config["SQLALCHEMY_DATABASE_URI"],
            binds=config.get("SQLALCHEMY_BINDS", {})
        )

    def _create_session_factory(self) -> None:
        self._session_factory = sessionmaker(binds=self.get_binds_mapping())
        self._session = scoped_session(self._session_factory)

    def _create_engine(self, uri, **kwargs) -> Engine:
        return create_engine(uri, **kwargs)

    def _get_binds_list(self) -> list[str | None]:
        return [None, *list(self.config.binds.keys())]

    def _get_tables_for_bind(self, bind: str = None) -> list:
        return [
            table for table in self.Model.metadata.tables.values()
            if table.info.get("bind_key", None) == bind
        ]

    def _get_uri_for_bind(self, bind: str = None) -> str:
        if bind is None:
            return self.config.uri
        binds: dict = self.config.binds
        if bind not in binds:
            warnings.warn(
                f"Bind {bind} is not defined by 'SQLALCHEMY_BINDS' in the "
                f"config, using 'SQLALCHEMY_DATABASE_URI' instead"
            )
            return self.config.uri
        return binds[bind]

    def _get_engine_for_bind(self, bind: str = None) -> Engine:
        engine = self._engines.get(bind, None)
        if engine is None:
            engine = self._create_engine(
                self._get_uri_for_bind(bind),
                convert_unicode=True,
                connect_args={"check_same_thread": False},
            )
            self._engines[bind] = engine
        return engine

    @contextmanager
    def scoped_session(self) -> Generator[Session, None, None]:
        session = self.session
        try:
            yield session
            session.commit()
        except Exception as e:
            self.rollback()
            raise e
        finally:
            self.close()

    def get_binds_mapping(self) -> dict:
        binds = self._get_binds_list()
        result = {}
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            result.update(
                {table: engine for table in self._get_tables_for_bind(bind)})
        return result

    def create_all(self) -> None:
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            self.Model.metadata.create_all(bind=engine, tables=tables)

    def drop_all(self) -> None:
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            self.Model.metadata.drop_all(bind=engine, tables=tables)

    def close(self) -> None:
        if self._session is None:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        self._session.remove()

    def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        self._session.rollback()


class AsyncSQLAlchemyWrapper(SQLAlchemyWrapper):
    def _create_session_factory(self) -> None:
        self._session_factory = sessionmaker(
            binds=self.get_binds_mapping(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
        self._session = async_scoped_session(self._session_factory, current_task)

    def _create_engine(self, uri, **kwargs) -> AsyncEngine:
        return create_async_engine(uri, **kwargs)

    @property
    def session(self) -> AsyncSession:
        if not self._session:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        else:
            return self._session()

    @asynccontextmanager
    async def scoped_session(self) -> AsyncGenerator[AsyncSession, None, None]:
        session = self.session
        try:
            yield session
            await session.commit()
        except Exception as e:
            await self.rollback()
            raise e
        finally:
            await self.close()

    async def create_all(self) -> None:
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            async with engine.begin() as conn:
                await conn.run_sync(
                    self.Model.metadata.create_all, tables=tables
                )

    async def drop_all(self) -> None:
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            async with engine.begin() as conn:
                await conn.run_sync(
                    self.Model.metadata.drop_all, tables=tables
                )

    async def close(self) -> None:
        if self._session is None:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        await self._session.remove()

    async def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        await self._session.rollback()
