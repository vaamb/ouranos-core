import typing as t

from fastapi import Depends, HTTPException, Query, status

from . import router
from src import api
from src.app.auth import is_admin
from src.app.dependencies import get_session


@router.get("/engine")
async def get_engines(
        engines_id: t.Optional[list[str]] = Query(default=None),
        session=Depends(get_session)
):
    engines = api.gaia.get_engines(session, engines_id)
    response = [api.gaia.get_engine_info(
        session, engine
    ) for engine in engines]
    return response


@router.get("/engine/u/<uid>")
async def get_engine(uid: str, session=Depends(get_session)):
    def exception():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Engine not found"
        )
    if uid == "all":
        exception()
    engine = api.gaia.get_engines(session, uid)
    if engine:
        response = api.gaia.get_engine_info(session, engine[0])
        return response
    exception()


@router.put("/engine/u/<uid>", dependencies=[Depends(is_admin)])
async def put_engine(
        uid: str,
        session=Depends(get_session),
):
    pass


@router.delete("/engine/u/<uid>", dependencies=[Depends(is_admin)])
async def delete_engine(
        uid: str,
        session=Depends(get_session),
):
    pass
