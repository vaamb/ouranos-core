import typing as t

from fastapi import HTTPException, Query, status

from . import db
from src import api


def get_session() -> t.Generator:
    try:
        yield db.session()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_time_window(
        start_time: t.Optional[str] = Query(default=None),
        end_time: t.Optional[str] = Query(default=None)
) -> api.utils.timeWindow:
    try:
        return api.utils.create_time_window(start_time, end_time)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'start_time' and 'end_time' should be valid iso times"
        )
