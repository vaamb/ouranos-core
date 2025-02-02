from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ouranos.core.database.models.gaia import Engine
from ouranos.web_server.auth import is_operator
from ouranos.web_server.dependencies import get_session
from ouranos.web_server.validate.gaia.engine import CrudRequestInfo, EngineInfo


router = APIRouter(
    prefix="/engine",
    responses={404: {"description": "Not found"}},
    tags=["gaia/engine"],
)


async def engine_or_abort(session: AsyncSession, engine_id: str) -> Engine:
    engine = await Engine.get_by_id(session, engine_id=engine_id)
    if engine:
        return engine
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No ecosystem(s) found"
    )


@router.get("", response_model=list[EngineInfo])
async def get_engines(
        *,
        engines_id: Annotated[
            list[str] | None,
            Query(description="A list of engine ids (either uids or sids) or "
                              "'recent' or 'connected'"),
        ] = None,
        session: Annotated[AsyncSession, Depends(get_session)],
):
    engines = await Engine.get_multiple_by_id(session, engines_id=engines_id)
    return engines


@router.get("/u/{uid}", response_model=EngineInfo)
async def get_engine(
        uid: Annotated[str, Path(description="An engine uid")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    engine = await engine_or_abort(session, uid)
    return engine


@router.delete("/u/{uid}",
               dependencies=[Depends(is_operator)])
async def delete_engine(
        uid: Annotated[str, Path(description="An engine uid")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    engine = await engine_or_abort(session, uid)
    await Engine.delete(session, engine.uid)
    return f"Engine {uid} deleted"


@router.get("/u/{uid}/crud_requests",
            response_model=list[CrudRequestInfo])
async def get_crud_requests(
        uid: Annotated[str, Path(description="An engine uid")],
        session: Annotated[AsyncSession, Depends(get_session)],
):
    engine = await engine_or_abort(session, uid)
    response = await engine.get_crud_requests(session)
    return response
