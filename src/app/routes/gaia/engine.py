import typing as t

from fastapi import Depends, HTTPException, Query, status

from . import router
from src import api
from src.app.auth import is_admin
from src.app.dependencies import get_session
from src.app.routes.utils import empty_result


async def engines_or_abort(session, engines):
    engines_qo = await api.gaia.get_engines(
        session=session, engines=engines
    )
    if engines_qo:
        return engines_qo
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


def assert_single_engine_id(engine_id):
    if "all" in engine_id or len(engine_id.split(",")) > 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="`engine_id` should be a single ecosystem name or uid"
        )


@router.get("/engine")
async def get_engines(
        engines_id: t.Optional[list[str]] = Query(default=None),
        session=Depends(get_session)
):
    engines = await api.gaia.get_engines(session, engines_id)
    response = [api.gaia.get_engine_info(
        session, engine
    ) for engine in engines]
    if response:
        return response
    return empty_result([])


@router.get("/engine/u/<uid>")
async def get_engine(uid: str, session=Depends(get_session)):
    assert_single_engine_id(uid)
    engine = await engines_or_abort(session, uid)
    if engine:
        response = api.gaia.get_engine_info(session, engine[0])
        return response
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Engine not found"
    )


@router.put("/engine/u/<uid>", dependencies=[Depends(is_admin)])
async def put_engine(
        uid: str,
        session=Depends(get_session),
):
    assert_single_engine_id(uid)
    engine = await engines_or_abort(session, uid)


@router.delete("/engine/u/<uid>", dependencies=[Depends(is_admin)])
async def delete_engine(
        uid: str,
        session=Depends(get_session),
):
    assert_single_engine_id(uid)
    engine = await engines_or_abort(session, uid)
