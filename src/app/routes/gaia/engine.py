import typing as t

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import router
from ..utils import assert_single_uid, empty_result
from src import api
from src.app.dependencies import get_session


async def engines_or_abort(session: AsyncSession, engines):
    engines_qo = await api.gaia.get_engines(
        session=session, engines=engines
    )
    if engines_qo:
        return engines_qo
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
    if response:
        return response
    return empty_result([])


@router.get("/engine/u/<uid>")
async def get_engine(
        uid: str,
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    engine = await engines_or_abort(session, uid)
    if engine:
        response = api.gaia.get_engine_info(session, engine[0])
        return response
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Engine not found"
    )
