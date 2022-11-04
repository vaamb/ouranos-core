import typing as t

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import router
from ..utils import assert_single_uid
from ouranos.api.dependencies import get_session
from ouranos import sdk

if t.TYPE_CHECKING:
    from ouranos.core.database.models.gaia import Engine


async def engine_or_abort(session: AsyncSession, engine_id: str) -> "Engine":
    engine = await sdk.engine.get(
        session=session, engine_id=engine_id
    )
    if engine:
        return engine
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("/engine")
async def get_engines(
        engines_id: t.Optional[list[str]] = Query(default=None),
        session: AsyncSession = Depends(get_session)
):
    engines = await sdk.engine.get_multiple(session, engines_id)
    response = [sdk.engine.get_info(
        session, engine
    ) for engine in engines]
    return response


@router.get("/engine/u/<uid>")
async def get_engine(
        uid: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    engine = await engine_or_abort(session, uid)
    response = sdk.engine.get_info(session, engine)
    return response
