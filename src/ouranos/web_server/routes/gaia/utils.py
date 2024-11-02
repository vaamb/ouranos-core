from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.gaia import Ecosystem


uids_desc = (
    "A list of ecosystem ids (either uids or names), or 'recent' or 'connected'")
h_level_desc = (
    "The sensor_level at which the sensor gathers data. Leave empty for both")
in_config_desc = (
    "Only select elements that are present (True) or also include the ones "
    "that have been removed (False) from the current gaia ecosystems config "
    "files")


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
