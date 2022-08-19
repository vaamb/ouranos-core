import typing as t

from . import db


def get_session() -> t.Generator:
    try:
        yield db.session()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
