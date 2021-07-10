import cachetools.func

from app.API.utils import time_limits
from app.models import Warning_table


@cachetools.func.ttl_cache(ttl=60)
def get_recent_warnings(session):
    time_limit = time_limits()["warnings"]

    return (session.query(Warning_table)
            .filter(Warning_table.datetime >= time_limit)
            .filter(Warning_table.solved == False)
            .order_by(Warning_table.level.desc())
            .order_by(Warning_table.id)
            .with_entities(Warning_table.datetime, Warning_table.emergency,
                           Warning_table.title)
            .all()
            )
