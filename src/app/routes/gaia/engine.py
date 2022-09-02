import typing as t

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import router
from ..utils import assert_single_uid
from src.app.dependencies import get_session
from src.core import api


if t.TYPE_CHECKING:
    from src.core.database.models.gaia import Engine


async def engine_or_abort(session: AsyncSession, engine_id: str) -> "Engine":
    engine = await api.gaia.get_engine(
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
    engines = await api.gaia.get_engines(session, engines_id)
    response = [api.gaia.get_engine_info(
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
    response = api.gaia.get_engine_info(session, engine)
    return response
