# Recipe adapted from https://flask.palletsprojects.com/en/1.1.x/patterns/sqlalchemy/
# and heavily inspired by Flask_SQLAlchemy.
# The recipe has been wrapped inside a class so it is more convenient.
# If working inside app context, DO NOT use this!


from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from utils import config_dict_from_class


_started: bool = False


class sqlalchemy_wrapper:
    """Wrapper to use SQLAlchemy in parallel of Flask-SQLAlchemy
    outside of app context

    For a safer use, use as follow:
    ``
    db = sqlalchemy_wrapper()
    with db.scoped_session() as session:
        session.your_query_here
    ``
    This will automatically create a scoped session and removed at the end of
    the query.
    """
    def __init__(self, config_class=None, uri=None, metadata=None, create=False):
        self._config = None
        if config_class is None and uri:
            self._config = {"SQLALCHEMY_DATABASE_URI": uri}
        elif config_class:
            self._config = config_dict_from_class(config_class)

        self.Model = declarative_base(name="Model", metadata=metadata)

        self._engines = {}
        self._sessions = {}

        if create:
            self.create_all()

    def init(self, config_class=None, uri=None):
        assert config_class or uri, "Please either provide a 'class_config' " \
                                    "or a database 'uri' parameter"
        if config_class is None:
            self._config = {"SQLALCHEMY_DATABASE_URI": uri}
        else:
            self._config = config_dict_from_class(config_class)

    def get_uri(self, bind=None):
        if bind is None:
            return self._config["SQLALCHEMY_DATABASE_URI"]
        binds = self._config.get("SQLALCHEMY_BINDS", ())
        assert bind in binds, f"Set bind {bind} in the config "\
                              f"'SQLALCHEMY_BINDS' in order to use it."
        return binds[bind]

    def get_engine(self, bind=None):
        assert self._config, "sqlalchemy_wrapper was not fully initialized"
        engine = self._engines.get(bind, None)
        if engine is None:
            engine = create_engine(self.get_uri(bind), convert_unicode=True)
            self._engines[bind] = engine
        return engine

    def create_session_maker(self, bind=None):
        return sessionmaker(bind=self.get_engine(bind))

    def get_session(self, bind=None):
        session = self._sessions.get(bind, None)
        if session is None:
            session = scoped_session(self.create_session_maker(bind=bind))
            self._sessions[bind] = session
        return session

    @property
    def engine(self):
        return self.get_engine()

    @property
    def session(self):
        return self.get_session()

    @contextmanager
    def scoped_session(self, bind=None):
        session = self.get_session(bind=bind)
        try:
            yield session
        except Exception as e:
            session.rollback()
            raise e
        finally:
            self.close_scope(bind=bind)

    def close_scope(self, bind="__all__"):
        if bind == "__all__":
            for session in self._sessions:
                self._sessions[session].remove()
        else:
            session = self.get_session(bind=bind)
            session.remove()

    def import_models(self):
        import app.models

    def create_all(self):
        self.import_models()
        self.Model.metadata.create_all(bind=self.engine)

    def drop_all(self):
        self.Model.metadata.drop_all(bind=self.engine)

    def add(self, *args, **kwargs):
        return self.session.add(*args, **kwargs)

    def commit(self):
        return self.session.commit()

    def rollback(self):
        return self.session.rollback()


db = sqlalchemy_wrapper()
"""

engines_db = sqlalchemy_wrapper(uri=Config.SQLALCHEMY_DATABASE_URI)
app_db = sqlalchemy_wrapper(uri=Config.SQLALCHEMY_BINDS["app"])
archive_db = sqlalchemy_wrapper(uri=Config.SQLALCHEMY_BINDS["archive"])

"""
