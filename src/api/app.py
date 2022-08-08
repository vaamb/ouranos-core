from typing import Union

from sqlalchemy import select
from sqlalchemy.orm.session import Session

from src.database.models.app import Service


def get_services(session: Session,
                 level: Union[list, tuple, str] = "all") -> list[dict]:
    if isinstance(level, str):
        level = level.split(",")
    if "all" in level:
        query = select(Service)
    else:
        query = select(Service).where(Service.level.in_(level))

    return [service.to_dict() for service in session.execute(query).scalars()]
