from fastapi import Depends

from . import router
from src import api
from src.app.auth import is_admin
from src.app.dependencies import get_session


@router.get("/engine")
async def get_engines(uid: list = ["all"], session=Depends(get_session)):
    engines = api.gaia.get_engines(session, uid)
    response = [api.gaia.get_engine_info(
        session, engine
    ) for engine in engines]
    return response


@router.get("/engine/u/<uid>")
async def get_engine(uid: str, session=Depends(get_session)):
    # TODO: make sure "all" is not used
    if uid == "all":
        return {"error": "Engine not found"}, 404
    engine = api.gaia.get_engines(session, uid)
    if engine:
        response = api.gaia.get_engine_info(session, engine[0])
        return response
    return {"error": "Engine not found"}, 404


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
