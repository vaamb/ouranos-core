# Recipe adapted from https://flask.palletsprojects.com/en/1.1.x/patterns/sqlalchemy/
# and heavily inspired by Flask_SQLAlchemy.
# The recipe has been wrapped inside a class to be more convenient.
# If working inside app context, DO NOT use this!


from __future__ import annotations

from asyncio import current_task
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy.engine import create_engine, Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_scoped_session
)
from sqlalchemy.orm import scoped_session, sessionmaker

from src.core.database._base import base


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
    _Model = base

    def __init__(
            self,
            config: type | str | dict | None = None,
            model=_Model,
    ):
        self.Model = model
        self._initialized = False
        self._session_factory = sessionmaker()
        self._session = scoped_session(None)  # For type hint only
        self._engines = {}
        self._config = None

        if config:
            self.init(config)

    @property
    def session(self):
        if not self._initialized:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        else:
            return self._session()

    def init(self, config_object: type | str | dict) -> None:
        self._init_config(config_object)
        self._create_session_factory()
        self._initialized = True

    def _init_config(self, config_object: type | str | dict):
        if isinstance(config_object, type):
            from config import config_dict_from_class
            self._config = config_dict_from_class(config_object)
        elif isinstance(config_object, str):
            self._config = {"SQLALCHEMY_DATABASE_URI": config_object}
        elif isinstance(config_object, dict):
            self._config = config_object
        else:
            raise TypeError("config_object can either be a str, a dict or a class")
        if "SQLALCHEMY_DATABASE_URI" not in self._config:
            raise ValueError(
                config_object
            )

    def _create_session_factory(self):
        self._session_factory = sessionmaker(binds=self.get_binds_mapping())
        self._session = scoped_session(self._session_factory)

    def _create_engine(self, uri, **kwargs):
        return create_engine(uri, **kwargs)

    def _get_binds_list(self) -> list:
        return [None] + list(self._config.get("SQLALCHEMY_BINDS", {}).keys())

    def _get_tables_for_bind(self, bind: str = None) -> list:
        return [
            table for table in self.Model.metadata.tables.values()
            if table.info.get("bind_key", None) == bind
        ]

    def _get_uri_for_bind(self, bind: str = None) -> str:
        if bind is None:
            return self._config["SQLALCHEMY_DATABASE_URI"]
        binds = self._config.get("SQLALCHEMY_BINDS", ())
        assert bind in binds, f"Set bind {bind} in the config "\
                              f"'SQLALCHEMY_BINDS' in order to use it."
        return binds[bind]

    def _get_engine_for_bind(self, bind: str = None) -> Engine:
        assert self._config, "SQLAlchemyWrapper has not been initialized"
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
    def scoped_session(self):
        try:
            yield self._session()
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

    def create_all(self):
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            self.Model.metadata.create_all(bind=engine, tables=tables)

    def drop_all(self):
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            self.Model.metadata.drop_all(bind=engine, tables=tables)

    def close(self):
        return self._session.remove()

    def rollback(self):
        return self._session.rollback()


class AsyncSQLAlchemyWrapper(SQLAlchemyWrapper):
    def _create_session_factory(self):
        self._session_factory = sessionmaker(
            binds=self.get_binds_mapping(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
        self._session = async_scoped_session(self._session_factory, current_task)

    def _create_engine(self, uri, **kwargs):
        return create_async_engine(uri, **kwargs)

    @asynccontextmanager
    async def scoped_session(self) -> AsyncSession:
        session: AsyncSession = self._session()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await self.rollback()
            raise e
        finally:
            await self.close()

    async def create_all(self):
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            async with engine.begin() as conn:
                await conn.run_sync(
                    self.Model.metadata.create_all, tables=tables
                )

    async def drop_all(self):
        binds = self._get_binds_list()
        for bind in binds:
            engine = self._get_engine_for_bind(bind)
            tables = self._get_tables_for_bind(bind)
            self.Model.metadata.drop_all(bind=engine, tables=tables)

    async def close(self):
        return await self._session.remove()

    async def rollback(self):
        return await self._session.rollback()