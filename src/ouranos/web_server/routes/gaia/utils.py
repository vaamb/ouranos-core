from fastapi import HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.gaia import Ecosystem


ecosystems_uid_q = Query(
    default=None,
    description="A list of ecosystem ids (either uids or names), or 'recent' "
                "or 'connected'"
)
hardware_level_q = Query(
    default=None,
    description="The sensor_level at which the sensor gathers data. Leave empty for both"
)


async def ecosystem_or_abort(
        session: AsyncSession,
        ecosystem_id: str,
) -> Ecosystem:
    ecosystem = await Ecosystem.get_by_id(session, ecosystem_id=ecosystem_id)
    if ecosystem:
        return ecosystem
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )
