from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.gaia import Engine
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.routes.utils import assert_single_uid
from ouranos.web_server.validate.response.base import (
    ResultResponse, ResultStatus)
from ouranos.web_server.validate.response.gaia import (
    CrudRequestInfo, EngineInfo)


router = APIRouter(
    prefix="/engine",
    responses={404: {"description": "Not found"}},
    tags=["gaia/engine"],
)


async def engine_or_abort(session: AsyncSession, engine_id: str) -> "Engine":
    engine = await Engine.get(
        session=session, engine_id=engine_id)
    if engine:
        return engine
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("", response_model=list[EngineInfo])
async def get_engines(
        engines_id: list[str] | None = Query(
            default=None, description="A list of engine ids (either uids or sids) or "
                                      "'recent' or 'connected'"),
        session: AsyncSession = Depends(get_session)
):
    engines = await Engine.get_multiple(session, engines_id)
    return engines


@router.get("/u/{uid}", response_model=EngineInfo)
async def get_engine(
        uid: str = Path(description="An engine uid"),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    engine = await engine_or_abort(session, uid)
    return engine


@router.delete("/u/{uid}",
               response_model=ResultResponse,
               dependencies=[Depends(is_operator)])
async def delete_engine(
        uid: str = Path(description="An engine uid"),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    engine = await engine_or_abort(session, uid)
    await Engine.delete(session, engine.uid)
    return ResultResponse(
        msg=f"Engine {uid} deleted",
        status=ResultStatus.success
    )


@router.get("/u/{uid}/crud_requests",
            response_model=list[CrudRequestInfo])
async def get_crud_requests(
        uid: str = Path(description="An engine uid"),
        session: AsyncSession = Depends(get_session)
):
    assert_single_uid(uid)
    engine = await engine_or_abort(session, uid)
    response = await engine.get_crud_requests(session)
    return response
