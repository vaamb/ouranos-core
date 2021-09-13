# Recipe adapted from https://flask.palletsprojects.com/en/1.1.x/patterns/sqlalchemy/
# and heavily inspired by Flask_SQLAlchemy.
# The recipe has been wrapped inside a class so it is more convenient.
# If working inside app context, DO NOT use this!


from contextlib import contextmanager

from flask_sqlalchemy.model import DefaultMeta, Model
from sqlalchemy.engine import create_engine, Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from src.utils import config_dict_from_class


class ArchiveMetaMixin(type):
    def __init__(cls, name, bases, d):
        archive_link = (
            d.pop('__archive_link__', None)
            or getattr(cls, '__archive_link__', None)
        )

        super(ArchiveMetaMixin, cls).__init__(name, bases, d)

        if archive_link is not None and getattr(cls, '__table__', None) is not None:
            cls.__table__.info['archive_link'] = archive_link


class CustomMeta(ArchiveMetaMixin, DefaultMeta):
    pass


Base = declarative_base(cls=Model, name="Model", metaclass=CustomMeta)


class SQLAlchemyWrapper:
    """Wrapper to use SQLAlchemy in parallel of Flask-SQLAlchemy
    outside of app context

    For a safe use, use as follow:
    ``
    db = SQLAlchemyWrapper()
    with db.scoped_session() as session:
        session.your_query_here
    ``
    This will automatically create a scoped session and remove it at the end of
    the scope.
    """
    _Model = Base

    def __init__(self, config=None, model=_Model, create=False):
        self.Model = model

        self._initialized = False
        self._session_factory = sessionmaker()
        self._session = scoped_session(None)  # For type hint only
        self._engines = {}
        self._config = None

        if config:
            self.init(config)

        if create:
            if not self._config:
                raise RuntimeError(
                    "Cannot create tables if no config is provided"
                )
            else:
                self.create_all()

    @property
    def session(self):
        if not self._initialized:
            raise RuntimeError(
                "No config option was provided. Use db.init(config) to finish "
                "db initialization"
            )
        else:
            return self._session

    def init(self, config_object) -> None:
        if isinstance(config_object, type):
            self._config = config_dict_from_class(config_object)
        elif isinstance(config_object, str):
            self._config = {"SQLALCHEMY_DATABASE_URI": config_object}
        elif isinstance(config_object, dict):
            self._config = config_object
        else:
            raise TypeError("config_object can either be a str, a dict or a class")
        assert "SQLALCHEMY_DATABASE_URI" in self._config
        self._session_factory.configure(binds=self.get_binds_mapping())
        self._session = scoped_session(self._session_factory)
        self._initialized = True

    def get_binds_mapping(self) -> dict:
        binds = [None] + list(self._config.get("SQLALCHEMY_BINDS", ()))
        tables = {}
        for bind in binds:
            tables.update({bind: []})
        for table in self.Model.metadata.tables.values():
            try:
                tables[table.info.get("bind_key")].append(table)
            except KeyError:
                print(f"Add {table.info.get('bind_key')} to the config"
                      f"'SQLALCHEMY_BINDS' in order to use it.")
        result = {}
        for bind in binds:
            engine = self.get_engine(bind)
            result.update({table: engine for table in tables[bind]})
        return result

    def get_uri(self, bind: str = None) -> str:
        if bind is None:
            return self._config["SQLALCHEMY_DATABASE_URI"]
        binds = self._config.get("SQLALCHEMY_BINDS", ())
        assert bind in binds, f"Set bind {bind} in the config "\
                              f"'SQLALCHEMY_BINDS' in order to use it."
        return binds[bind]

    def get_engine(self, bind: str = None) -> Engine:
        assert self._config, "sqlalchemy_wrapper was not fully initialized"
        engine = self._engines.get(bind, None)
        if engine is None:
            engine = create_engine(self.get_uri(bind), convert_unicode=True)
            self._engines[bind] = engine
        return engine

    @contextmanager
    def scoped_session(self):
        try:
            yield self.session
        except Exception as e:
            self.session.rollback()
            raise e
        finally:
            self.session.remove()

    def create_all(self):
        self.Model.metadata.create_all()

    def drop_all(self):
        self.Model.metadata.drop_all()

    def add(self, *args, **kwargs):
        return self.session.add(*args, **kwargs)

    def commit(self):
        return self.session.commit()

    def rollback(self):
        return self.session.rollback()

    def close(self):
        return self.session.remove()
