import cachetools.func

from src.app.API.utils import time_limits
from src.app.models import EcosystemWarning


@cachetools.func.ttl_cache(ttl=60)
def get_recent_warnings(session, limit: int = 10) -> list[EcosystemWarning]:
    time_limit = time_limits()["warnings"]

    return (session.query(EcosystemWarning)
            .filter(EcosystemWarning.created >= time_limit)
            .filter(EcosystemWarning.solved is None)
            .order_by(EcosystemWarning.level.desc())
            .order_by(EcosystemWarning.id)
            .with_entities(EcosystemWarning.created, EcosystemWarning.emergency,
                           EcosystemWarning.title)
            .limit(limit)
            .all()
            )


def check_any_recent_warnings(session) -> bool:
    time_limit = time_limits()["warnings"]
    return bool(
        session.query(EcosystemWarning)
               .filter(EcosystemWarning.created >= time_limit)
               .filter(EcosystemWarning.solved is None)
               .first()
    )
