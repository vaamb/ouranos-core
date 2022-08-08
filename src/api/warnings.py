import cachetools.func

from src.api.utils import time_limits
from src.database.models.app import AppWarning


@cachetools.func.ttl_cache(ttl=60)
def get_recent_warnings(session, limit: int = 10) -> list[AppWarning]:
    time_limit = time_limits()["warnings"]
    return (session.query(AppWarning)
            .filter(AppWarning.created >= time_limit)
            .filter(AppWarning.solved is None)
            .order_by(AppWarning.level.desc())
            .order_by(AppWarning.id)
            .with_entities(AppWarning.created, AppWarning.emergency,
                           AppWarning.title)
            .limit(limit)
            .all()
            ) or []


def check_any_recent_warnings(session) -> bool:
    time_limit = time_limits()["warnings"]
    return bool(
        session.query(AppWarning)
               .filter(AppWarning.created >= time_limit)
               .filter(AppWarning.solved is None)
               .first()
    )
